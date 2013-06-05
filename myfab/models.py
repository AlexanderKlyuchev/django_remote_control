from django.db import models
import socket
from exceptions import NetworkError


import os
import os.path
import posixpath
import re
import subprocess
import sys
import time

from myfab.io import output_loop
from thread_handling import ThreadHandler
from django.conf import settings
from django.core.cache import cache

try:
    import warnings
    warnings.simplefilter('ignore', DeprecationWarning)
    import paramiko as ssh
    if getattr(settings, 'SSH_LOGGING_ENABLED', None):
       ssh.util.log_to_file("ssh.log")
except ImportError, e:
    import traceback
    traceback.print_exc()
    msg = """
There was a problem importing our SSH library (see traceback above).
Please make sure all dependencies are installed and importable.
""".rstrip()
    sys.stderr.write(msg + '\n')
    sys.exit(1)

OSs= (
    ('Win2003', 'Wind2003'),
    ('Ubuntu', 'Ubuntu'),
    ('CentOS', 'CentOS'),
    ('MacOS', 'MacOS'),
)

HostConnectionCache={}

class Server(models.Model):
    """ Docstring """
    name = models.CharField(max_length=128, verbose_name=('Name'),unique=True)
    address=models.IPAddressField()
    username=models.CharField(max_length=32)
    password=models.CharField(max_length=32)
    port=models.IntegerField(default=22,blank=True)
    key_file=models.FileField(upload_to="key_files",blank=True)
    os=models.CharField(max_length=20, choices=OSs)
    

    def __unicode__(self):
        return u'%s' % self.name

    @classmethod
    def get_all_servers(cls):
        key = 'Servers.AllCachedServers.Key'
        servers = cache.get(key)
        if servers is None:
            servers= list(Server.objects.values_list('id', flat=True))
            cache.set(key, servers)
        return servers
    
    def execute(self,channel, command, combine_stderr=None,
          stdout=None, stderr=None, timeout=None):
        # Combine stdout and stderr to get around oddball mixing issues
        if combine_stderr is None:
	   combine_stderr=getattr(settings,'COMBINE_STD_ERR',None)
        
        channel.set_combine_stderr(combine_stderr)

        timeout=getattr(settings,'COMMAND_TIMEOUT',4) if not timeout else timeout
        # stdout/stderr redirection
        stdout = stdout or sys.stdout
        stderr = stderr or sys.stderr


        channel.exec_command(command=command)
        # Init stdout, stderr capturing. Must use lists instead of strings as
        # strings are immutable and we're using these as pass-by-reference
        stdout_buf, stderr_buf = [], []
        workers = (
            ThreadHandler('out', output_loop, channel, "recv",
                capture=stdout_buf, stream=sys.stdout, timeout=timeout),
            ThreadHandler('err', output_loop, channel, "recv_stderr",
                capture=stderr_buf, stream=sys.stderr, timeout=timeout),
        )


        while True:
            if channel.exit_status_ready():
                break
            else:
                # Check for thread exceptions here so we can raise ASAP
                # (without chance of getting blocked by, or hidden by an
                # exception within, recv_exit_status())
                for worker in workers:
                    worker.raise_if_needed()
            try:
                time.sleep(ssh.io_sleep)
            except KeyboardInterrupt:
                if not remote_interrupt:
                    raise
                channel.send('\x03')

        # Obtain exit code of remote program now that we're done.
        status = channel.recv_exit_status()
        # Wait for threads to exit so we aren't left with stale threads
        for worker in workers:
            worker.thread.join()
            worker.raise_if_needed()

        # Close channel
        channel.close()

        stdout_buf = ''.join(stdout_buf).strip()
        stderr_buf = ''.join(stderr_buf).strip()

        return stdout_buf, stderr_buf, status

    def open_session(self):
      return self.cached_connect().get_transport().open_session()


    def default_channel(self):
      try:
        chan = self.open_session()
      except ssh.SSHException, err:
        if str(err) == 'SSH session not active':
            HostConnectionCache[self.name].close()
            del HostConnectionCache[self.name] 
            chan = open_session(host)
        else:
            raise
      chan.settimeout(0.1)
      chan.input_enabled = True
      return chan

    def cached_connect(self):
        if self.name in HostConnectionCache:
           return HostConnectionCache[self.name] 
        else:
	  connection=self.connect()
          HostConnectionCache[self.name]=connection 
          return connection 

    def connect(self,port='',sock=None):
      """
        Create and return a new SSHClient instance connected to given host.

        If ``sock`` is given, it's passed into ``SSHClient.connect()`` directly.
        Used for gateway connections by e.g. ``HostConnectionCache``.
      """
      #
      # Initialization
      #

      # Init client
      client = ssh.SSHClient()

      # Load known host keys (e.g. ~/.ssh/known_hosts) unless user says not to.
      client.load_system_host_keys()
      # Unless user specified not to, accept/add new, unknown host keys
      client.set_missing_host_key_policy(ssh.AutoAddPolicy())

      #
      # Connection attempt loop
      #

      # Initialize loop variables
      connected = False
      tries = 0


      # Loop until successful connect (keep prompting for new password)
      while not connected:
        # Attempt connection
        try:
            tries += 1
            
            client.connect(
                hostname=self.address,
                port=self.port if self.port else 22,
                username=self.username,
                password=self.password,
                key_filename=self.key_file.url if self.key_file else None,
                timeout=getattr(settings,'CONNECTION_TIMEOUT',3),
                allow_agent=True,
                look_for_keys=False,
                sock=sock
            )
            connected = True

            # set a keepalive if desired
            keepalive=getattr(settings,'KEEP_ALIVE',None)
            if keepalive:
               client.get_transport().set_keepalive(keepalive)

            return client
        # BadHostKeyException corresponds to key mismatch, i.e. what on the
        # command line results in the big banner error about man-in-the-middle
        # attacks.
        except ssh.BadHostKeyException, e:
            raise NetworkError("Host key for %s did not match pre-existing key! Server's key was changed recently, or possible man-in-the-middle attack." % host, e)
        except (
            ssh.AuthenticationException,
            ssh.PasswordRequiredException,
            ssh.SSHException
        ), e:
            msg = str(e)
            raise NetworkError(msg, e)
        # Handle DNS error / name lookup failure
        except socket.gaierror, e:
            raise NetworkError('Name lookup failed for %s' % host, e)
        # Handle timeouts and retries, including generic errors
        # NOTE: In 2.6, socket.error subclasses IOError
        except socket.error, e:
            not_timeout = type(e) is not socket.timeout
            connection_attempts=getattr(settings,'CONNECTION_ATTEMPTS',1)
            giving_up = tries >= connection_attempts 
            # Baseline error msg for when debug is off
            msg = "Timed out trying to connect to %s" % self.address 
            # Expanded for debug on
            err = msg + " (attempt %s of %s)" % (tries, connection_attempts)
            if giving_up:
                err += ", giving up"
            err += ")"
            if not giving_up:
                # Sleep if it wasn't a timeout, so we still get timeout-like
                # behavior
                if not_timeout:
                    time.sleep(env.timeout)
                continue
            # Override eror msg if we were retrying other errors
            if not_timeout:
                msg = "Low level socket error connecting to host %s on port %s: %s" % (
                    self.address, 22, e[1]
                )
            # Here, all attempts failed. Tweak error msg to show # tries.
            s = "s" if connection_attempts > 1 else ""
            msg += " (tried %s time%s)" % (connection_attempts, s)
            raise NetworkError(msg, e)
        # Ensure that if we terminated without connecting and we were given an
        # explicit socket, close it out.
        finally:
            if not connected and sock is not None:
                sock.close()
