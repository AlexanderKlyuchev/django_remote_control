Overview:
  App is intended to execute commands on remote servers.
  It is based on django core engine to handle users requests
  and on paramico open source lib for communication with remote 
  servers over ssh protocol.
  Frontend interface extends django admin interface routine.
  Servers configuration is moved to database so admin
  users can add new servers and edit their configuration(ip,name, connection port, user, password) at any time.
  Num of max servsers may be limited  overriding method save() of Server model class.
  Every configuration parameters is read from setings.py
  Also it may be done separated model for configuration to read  config parameters from database.
  To limit num of simultaneous operation on each server used semaphores.
  The semaphores used in nonblocking mode. But it may be configured timeout to try waiting
  some time until server will be free.
  Dictionary used for mapping between semaphores and servers.
  It  initializes in startapp phase and changes automaticaly when new servers added via signals post_save handler.
  3 kind of exceptions may be thrown during operation execution:
     CommandTimeOut- if time of command execution limit is exhausted
     NetworkError - if some troubles with connection to server
     RequestTimeOut - if time of  all commands execution limit is exhausted
  Or if semaphore for server is blocked - 'server is busy' status string returned for correspond server  
  useful settings parameters you may want to configure:
  'RESPONSE_TIMEOUT'- timeout to get response
  'NUM_CONC_OPERATIONS'-num of operations  may be executed  on each server simultaneously
  'NUM_CONC_USERS'- num of users may work with service simultaneously
  'COMMAND_TIMEOUT'- timeout for command execution
  'CONNECTION_TIMEOUT'- ...
  'CONNECTION_ATTEMPTS'- num of attempts to connect in case of failure
  'SSH_LOGGING_ENABLED'-...
  
