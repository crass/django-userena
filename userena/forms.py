from django import forms
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils.hashcompat import sha_constructor

from userena import settings as userena_settings
from userena.models import UserenaSignup
from userena.utils import get_profile_model, generate_valid_random_username

import random

attrs_dict = {'class': 'required'}

USERNAME_RE = r'^[\.\w]+$'

class SignupForm(forms.Form):
    """
    Form for creating a new user account.

    Validates that the requested username and e-mail is not already in use.
    Also requires the password to be entered twice and the Terms of Service to
    be accepted.

    """
    username = forms.RegexField(regex=USERNAME_RE,
                                max_length=30,
                                widget=forms.TextInput(attrs=attrs_dict),
                                label=_("Username"),
                                error_messages={'invalid': _('Username must contain only letters, numbers, dots and underscores.')})
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=75)),
                             label=_("Email"),
                             error_messages={
                                'unique_activated': _('This email address is already associated '
                                                      'with an activated user account. Use the '
                                                      '"Sign-in form" or "Forgot my password" links.'),
                                'unique_unactivated': _('This email address is already associated'
                                                        ' with a user account, but the account has not'
                                                        ' been activated. An email with an activation'
                                                        ' link was resent to you. Check that your '
                                                        'spam filter did not catch this message.'),
                             })
    password1 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Create password"))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict,
                                                           render_value=False),
                                label=_("Repeat password"))

    def clean_username(self):
        """
        Validate that the username is alphanumeric and is not already in use.
        Also validates that the username is not listed in
        ``USERENA_FORBIDDEN_USERNAMES`` list.

        """
        try:
            user = User.objects.get(username__iexact=self.cleaned_data['username'])
        except User.DoesNotExist:
            pass
        else:
            raise forms.ValidationError(_('This username is already taken.'))
        if self.cleaned_data['username'].lower() in userena_settings.USERENA_FORBIDDEN_USERNAMES:
            raise forms.ValidationError(_('This username is not allowed.'))
        return self.cleaned_data['username']

    def clean_email(self):
        """ Validate that the e-mail address is unique. """
        try:
            u = User.objects.select_related('userena_signup') \
                            .get(email__iexact=self.cleaned_data['email'])
        except User.DoesNotExist:
            return self.cleaned_data['email']
        
        email_error_messages = self.fields['email'].error_messages
        if userena_settings.USERENA_ACTIVATION_RESEND_ON_SIGNUP \
           and not u.userena_signup.has_activated():
            self.signup = u.userena_signup
            raise forms.ValidationError(email_error_messages['unique_unactivated'])
        
        raise forms.ValidationError(email_error_messages['unique_activated'])

    def clean(self):
        """
        Validates that the values entered into the two password fields match.
        Note that an error here will end up in ``non_field_errors()`` because
        it doesn't apply to a single field.

        """
        if 'password1' in self.cleaned_data and 'password2' in self.cleaned_data:
            if self.cleaned_data['password1'] != self.cleaned_data['password2']:
                raise forms.ValidationError(_('The two password fields didn\'t match.'))
        return self.cleaned_data

    def save(self):
        """ Creates a new user and account. Returns the newly created user. """
        new_user = UserenaSignup.objects.create_user(self.cleaned_data,
                                                     not userena_settings.USERENA_ACTIVATION_REQUIRED,
                                                     userena_settings.USERENA_ACTIVATION_REQUIRED)
        return new_user

class SignupFormOnlyEmail(SignupForm):
    """
    Form for creating a new user account but not needing a username.

    This form is an adaptation of :class:`SignupForm`. It's used when
    ``USERENA_WITHOUT_USERNAME`` setting is set to ``True``. And thus the user
    is not asked to supply an username, but one is generated for them. The user
    can than keep sign in by using their email.

    """
    def __init__(self, *args, **kwargs):
        super(SignupFormOnlyEmail, self).__init__(*args, **kwargs)
        del self.fields['username']

    def save(self):
        """ Generate a random username before falling back to parent signup form """
        self.cleaned_data['username'] = generate_valid_random_username()
        return super(SignupFormOnlyEmail, self).save()

class SignupFormTos(SignupForm):
    """ Add a Terms of Service button to the ``SignupForm``. """
    tos = forms.BooleanField(widget=forms.CheckboxInput(attrs=attrs_dict),
                             label=_(u'I have read and agree to the Terms of Service'),
                             error_messages={'required': _('You must agree to the terms to register.')})

def identification_field_factory(label, error_required):
    """
    A simple identification field factory which enable you to set the label.

    :param label:
        String containing the label for this field.

    :param error_required:
        String containing the error message if the field is left empty.

    """
    return forms.CharField(label=_("%(label)s") % {'label': label},
                           widget=forms.TextInput(attrs=attrs_dict),
                           max_length=75,
                           error_messages={'required': _("%(error)s") % {'error': error_required}})

class AuthenticationForm(forms.Form):
    """
    A custom form where the identification can be a e-mail address or username.

    """
    identification = identification_field_factory(_(u"Email or username"),
                                                  _(u"Either supply us with your email or username."))
    password = forms.CharField(label=_("Password"),
                               widget=forms.PasswordInput(attrs=attrs_dict, render_value=False))
    remember_me = forms.BooleanField(widget=forms.CheckboxInput(attrs=attrs_dict),
                                     required=False,
                                     label=_(u'Remember me for %(days)s') % {'days': _(userena_settings.USERENA_REMEMBER_ME_DAYS[0])})

    def __init__(self, *args, **kwargs):
        """ A custom init because we need to change the label if no usernames is used """
        super(AuthenticationForm, self).__init__(*args, **kwargs)
        if userena_settings.USERENA_WITHOUT_USERNAMES:
            self.fields['identification'] = identification_field_factory(_(u"Email"),
                                                                         _(u"Please supply your email."))

    def clean(self):
        """
        Checks for the identification and password.

        If the combination can't be found will raise an invalid sign in error.

        """
        identification = self.cleaned_data.get('identification')
        password = self.cleaned_data.get('password')

        if identification and password:
            user = authenticate(identification=identification, password=password)
            if user is None:
                raise forms.ValidationError(_(u"Please enter a correct username or email and password. Note that both fields are case-sensitive."))
        return self.cleaned_data

class ChangeEmailForm(forms.Form):
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=75)),
                             label=_(u"New email"))

    def __init__(self, user, *args, **kwargs):
        """
        The current ``user`` is needed for initialisation of this form so
        that we can check if the email address is still free and not always
        returning ``True`` for this query because it's the users own e-mail
        address.

        """
        super(ChangeEmailForm, self).__init__(*args, **kwargs)
        if not isinstance(user, User):
            raise TypeError, "user must be an instance of User"
        else: self.user = user

    def clean_email(self):
        """ Validate that the email is not already registered with another user """
        if self.cleaned_data['email'].lower() == self.user.email:
            raise forms.ValidationError(_(u'You\'re already known under this email.'))
        if User.objects.filter(email__iexact=self.cleaned_data['email']).exclude(email__iexact=self.user.email):
            raise forms.ValidationError(_(u'This email is already in use. Please supply a different email.'))
        return self.cleaned_data['email']

    def save(self):
        """
        Save method calls :func:`user.change_email()` method which sends out an
        email with an verification key to verify and with it enable this new
        email address.

        """
        return self.user.userena_signup.change_email(self.cleaned_data['email'])

class EditProfileForm(forms.ModelForm):
    """ Base form used for fields that are always required """
    first_name = forms.CharField(label=_(u'First name'),
                                 max_length=30,
                                 required=False)
    last_name = forms.CharField(label=_(u'Last name'),
                                max_length=30,
                                required=False)
    user_fields = ('first_name', 'last_name')

    def __init__(self, *args, **kw):
        super(EditProfileForm, self).__init__(*args, **kw)
        # Put the user fields at the top
        new_order = list(self.user_fields) + \
                    [f for f in self.fields.keyOrder \
                       if f not in self.user_fields]
        self.fields.keyOrder = new_order

    class Meta:
        model = get_profile_model()
        exclude = ['user']

    def save(self, force_insert=False, force_update=False, commit=True):
        profile = super(EditProfileForm, self).save(commit=commit)
        # Save user fields
        user = profile.user
        for user_field_name in self.user_fields:
            setattr(user, user_field_name, self.cleaned_data[user_field_name])
        if commit:
            user.save()

        return profile
