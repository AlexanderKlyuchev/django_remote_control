from django import forms
from django.contrib.humanize.templatetags.humanize import apnumber
from django.template.defaultfilters import pluralize

from django.db import models
from django.utils.text import capfirst
from django.core import exceptions
from myfab.models import Server

#from contentitems.forms import MultiSelectFormField

class Console(forms.Form):
        OPTIONS = (
            ("a", "A"),
            ("b", "B"),
            )
        servers = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                         queryset = Server.objects.all(),required=True)
        command = forms.CharField()
