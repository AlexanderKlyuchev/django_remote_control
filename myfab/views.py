from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.template import RequestContext

from forms import Console 
from models import Server
import threading
import time
from django.db.models.signals import post_save
from django.conf import settings
from exceptions import NetworkError,CommandTimeout,UserResponseTimeout


num_of_concurent_operations=getattr(settings,'NUM_CONC_OPERATIONS', 1)
num_of_concurent_users=getattr(settings,'NUM_CONC_USERS', 10)
users_semaphore=threading.Semaphore(num_of_concurent_users)


def init_serv_sems():
   servers=Server.get_all_servers()
   semaphors=[threading.Semaphore(num_of_concurent_operations)]*len(servers)
   return dict(zip(servers,semaphors))

serv_semaphores=init_serv_sems()

def server_update_handler(sender, **kwargs):
  if kwargs['created']:
     serv_semaphores.update({kwargs['instance'].id:threading.Semaphore(num_of_concurent_operations)})

def disconnect_all():
    """
    Disconnect from all currently connected servers.
    """
    from myfab.models import HostConnectionCache as connections
    # Explicitly disconnect from all servers
    for key in connections.keys():
        connections[key].close()
        del connections[key]


@login_required
def home(request):  
    users_semaphore.acquire()
    results_list=[]
    if request.POST:
        form = Console(request.POST)
        if form.is_valid():
           selected_servers=request.POST.getlist("servers")
	   servers=Server.objects.filter(id__in=selected_servers)
           command=form.cleaned_data['command'] 
           response_timeout=getattr(settings,'RESPONSE_TIMEOUT',100)
           start = time.time()
           for server in servers:
               if serv_semaphores[server.id].acquire(blocking=False):
                 try:
                   elapsed = time.time() - start
                   if response_timeout is not None and elapsed > response_timeout:
                      raise UserResponseTimeout
                   channel=server.default_channel()
                   stdout_buf, stderr_buf, status=server.execute(channel=channel, command=command)
                   results_list.append((server.name,stdout_buf))
                   serv_semaphores[server.id].release()
                 except NetworkError as err:
                   results_list.append((server.name,err.message))
                 except CommandTimeout:
                   results_list.append((server.name,'Command timeout'))
                 except UserResponseTimeout:
                   results_list.append(('%s-%s'%(server.name,servers[-1].name),'Response timeout expired and commands werent executed')) 
                 finally:
                   serv_semaphores[server.id].release()
               else:
                  results_list.append((server.name,"server is busy"))#we cant execute more than 2 operations at once
    
    else:
        form=Console()
    users_semaphore.release()
    template="registration/login.html"
    return render(request, "main.html", {
        'form':form,
    'results':results_list 
    })

post_save.connect(server_update_handler, sender=Server)
