from django import forms
from django.db import models
from myfab.models import Server


class Console(forms.Form):
        servers = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                         queryset = Server.objects.all(),required=True)
        command = forms.CharField()
