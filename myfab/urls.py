from django.conf.urls import patterns, include, url
from django.contrib.auth.views import login

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
     url(r'^$', 'myfab.views.home', name='home'),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^accounts/login/$',  login),

    # Uncomment the next line to enable the admin:
     url(r'^admin/', include(admin.site.urls)),
)
