from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.core.mail import send_mail
from django.core.exceptions import ImproperlyConfigured

from userena.utils import get_gravatar, generate_sha1, get_protocol
from userena.managers import UserenaManager, UserenaBaseProfileManager
from userena.models_base import UserenaBaseProfile, UserenaMugshotBaseProfile
from userena import settings as userena_settings

from guardian.shortcuts import get_perms
from guardian.shortcuts import assign

import datetime, random


class UserenaSignup(models.Model):
    """
    Userena model which stores all the necessary information to have a full
    functional user implementation on your Django website.

    """
    user = models.OneToOneField(User,
                                verbose_name=_('user'),
                                related_name='userena_signup')

    last_active = models.DateTimeField(_('last active'),
                                       blank=True,
                                       null=True,
                                       help_text=_('The last date that the user was active.'))

    activation_key = models.CharField(_('activation key'),
                                      max_length=40,
                                      blank=True)

    activation_notification_send = models.BooleanField(_('notification send'),
                                                       default=False,
                                                       help_text=_('Designates whether this user has already got a notification about activating their account.'))

    email_unconfirmed = models.EmailField(_('unconfirmed email address'),
                                          blank=True,
                                          help_text=_('Temporary email address when the user requests an email change.'))

    email_confirmation_key = models.CharField(_('unconfirmed email verification key'),
                                              max_length=40,
                                              blank=True)

    email_confirmation_key_created = models.DateTimeField(_('creation date of email confirmation key'),
                                                          blank=True,
                                                          null=True)


    objects = UserenaManager()

    class Meta:
        verbose_name = _('userena registration')
        verbose_name_plural = _('userena registrations')

    def __unicode__(self):
        return '%s' % self.user.username

    def change_email(self, email):
        """
        Changes the email address for a user.

        A user needs to verify this new email address before it becomes
        active. By storing the new email address in a temporary field --
        ``temporary_email`` -- we are able to set this email address after the
        user has verified it by clicking on the verification URI in the email.
        This email gets send out by ``send_verification_email``.

        :param email:
            The new email address that the user wants to use.

        """
        self.email_unconfirmed = email

        salt, hash = generate_sha1(self.user.username)
        self.email_confirmation_key = hash
        self.email_confirmation_key_created = datetime.datetime.now()
        self.save()

        # Send email for activation
        self.send_confirmation_email()

    def send_confirmation_email(self):
        """
        Sends an email to confirm the new email address.

        This method sends out two emails. One to the new email address that
        contains the ``email_confirmation_key`` which is used to verify this
        this email address with :func:`UserenaUser.objects.confirm_email`.

        The other email is to the old email address to let the user know that
        a request is made to change this email address.

        """
        context= {'user': self.user,
                  'new_email': self.email_unconfirmed,
                  'protocol': get_protocol(),
                  'confirmation_key': self.email_confirmation_key,
                  'site': Site.objects.get_current()}


        # Email to the old address
        subject_old = render_to_string('userena/emails/confirmation_email_subject_old.txt',
                                       context)
        subject_old = ''.join(subject_old.splitlines())

        message_old = render_to_string('userena/emails/confirmation_email_message_old.txt',
                                       context)

        send_mail(subject_old,
                  message_old,
                  settings.DEFAULT_FROM_EMAIL,
                  [self.user.email])

        # Email to the new address
        subject_new = render_to_string('userena/emails/confirmation_email_subject_new.txt',
                                       context)
        subject_new = ''.join(subject_new.splitlines())

        message_new = render_to_string('userena/emails/confirmation_email_message_new.txt',
                                       context)

        send_mail(subject_new,
                  message_new,
                  settings.DEFAULT_FROM_EMAIL,
                  [self.email_unconfirmed,])

    def activation_key_expired(self):
        """
        Checks if activation key is expired.

        Returns ``True`` when the ``activation_key`` of the user is expired and
        ``False`` if the key is still valid.

        The key is expired when it's set to the value defined in
        ``USERENA_ACTIVATED`` or ``activation_key_created`` is beyond the
        amount of days defined in ``USERENA_ACTIVATION_DAYS``.

        """
        expiration_days = datetime.timedelta(days=userena_settings.USERENA_ACTIVATION_DAYS)
        expiration_date = self.user.date_joined + expiration_days
        if self.activation_key == userena_settings.USERENA_ACTIVATED:
            return True
        if datetime.datetime.now() >= expiration_date:
            return True
        return False

    def send_activation_email(self):
        """
        Sends a activation email to the user.

        This email is send when the user wants to activate their newly created
        user.

        """
        context= {'user': self.user,
                  'protocol': get_protocol(),
                  'activation_days': userena_settings.USERENA_ACTIVATION_DAYS,
                  'activation_key': self.activation_key,
                  'site': Site.objects.get_current()}

        subject = render_to_string('userena/emails/activation_email_subject.txt',
                                   context)
        subject = ''.join(subject.splitlines())

        message = render_to_string('userena/emails/activation_email_message.txt',
                                   context)
        send_mail(subject,
                  message,
                  settings.DEFAULT_FROM_EMAIL,
                  [self.user.email,])

