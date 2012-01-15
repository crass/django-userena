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
from userena import settings as userena_settings

from guardian.shortcuts import get_perms
from guardian.shortcuts import assign

PROFILE_PERMISSIONS = (
            ('view_profile', 'Can view profile'),
)

class UserenaBaseProfile(models.Model):
    """ Base model needed for extra profile functionality """
    PRIVACY_CHOICES = (
        ('open', _('Open')),
        ('registered', _('Registered')),
        ('closed', _('Closed')),
    )

    privacy = models.CharField(_('privacy'),
                               max_length=15,
                               choices=PRIVACY_CHOICES,
                               default=userena_settings.USERENA_DEFAULT_PRIVACY,
                               help_text = _('Designates who can view your profile.'))

    objects = UserenaBaseProfileManager()


    class Meta:
        """
        Meta options making the model abstract and defining permissions.

        The model is ``abstract`` because it only supplies basic functionality
        to a more custom defined model that extends it. This way there is not
        another join needed.

        We also define custom permissions because we don't know how the model
        that extends this one is going to be called. So we don't know what
        permissions to check. For ex. if the user defines a profile model that
        is called ``MyProfile``, than the permissions would be
        ``add_myprofile`` etc. We want to be able to always check
        ``add_profile``, ``change_profile`` etc.

        """
        abstract = True
        permissions = PROFILE_PERMISSIONS

    def __unicode__(self):
        return 'Profile of %(username)s' % {'username': self.user.username}

    def get_full_name_or_username(self):
        """
        Returns the full name of the user, or if none is supplied will return
        the username.

        Also looks at ``USERENA_WITHOUT_USERNAMES`` settings to define if it
        should return the username or email address when the full name is not
        supplied.

        :return:
            ``String`` containing the full name of the user. If no name is
            supplied it will return the username or email address depending on
            the ``USERENA_WITHOUT_USERNAMES`` setting.

        """
        user = self.user
        if user.first_name or user.last_name:
            # We will return this as translated string. Maybe there are some
            # countries that first display the last name.
            name = _("%(first_name)s %(last_name)s") % \
                {'first_name': user.first_name,
                 'last_name': user.last_name}
        else:
            # Fallback to the username if usernames are used
            if not userena_settings.USERENA_WITHOUT_USERNAMES:
                name = "%(username)s" % {'username': user.username}
            else:
                name = "%(email)s" % {'email': user.email}
        return name.strip()

    def can_view_profile(self, user):
        """
        Can the :class:`User` view this profile?

        Returns a boolean if a user has the rights to view the profile of this
        user.

        Users are divided into four groups:

            ``Open``
                Everyone can view your profile

            ``Closed``
                Nobody can view your profile.

            ``Registered``
                Users that are registered on the website and signed
                in only.

            ``Admin``
                Special cases like superadmin and the owner of the profile.

        Through the ``privacy`` field a owner of an profile can define what
        they want to show to whom.

        :param user:
            A Django :class:`User` instance.

        """
        # Simple cases first, we don't want to waste CPU and DB hits.
        # Everyone.
        if self.privacy == 'open': return True
        # Registered users.
        elif self.privacy == 'registered' and isinstance(user, User):
            return True

        # Checks done by guardian for owner and admins.
        elif 'view_profile' in get_perms(user, self):
            return True

        # Fallback to closed profile.
        return False

def upload_to_mugshot(instance, filename):
    """
    Uploads a mugshot for a user to the ``USERENA_MUGSHOT_PATH`` and saving it
    under unique hash for the image. This is for privacy reasons so others
    can't just browse through the mugshot directory.

    """
    extension = filename.split('.')[-1].lower()
    salt, hash = generate_sha1(instance.id)
    return '%(path)s%(hash)s.%(extension)s' % {'path': userena_settings.USERENA_MUGSHOT_PATH,
                                               'hash': hash[:10],
                                               'extension': extension}

#imp.find_module('recaptcha_works')

try:
    #easy_thumbnails = __import__("easy_thumbnails.fields", fromlist=['ThumbnailerImageField'])
    from easy_thumbnails.fields import ThumbnailerImageField
except ImportError:
    pass
else:
    class UserenaMugshotBaseProfile(UserenaBaseProfile):
        MUGSHOT_SETTINGS = {'size': (userena_settings.USERENA_MUGSHOT_SIZE,
                                     userena_settings.USERENA_MUGSHOT_SIZE),
                            'crop': 'smart'}
        
        
        mugshot = ThumbnailerImageField(_('mugshot'),
                                        blank=True,
                                        upload_to=upload_to_mugshot,
                                        resize_source=MUGSHOT_SETTINGS,
                                        help_text=_('A personal image displayed in your profile.'))
        
        class Meta(UserenaBaseProfile.Meta):
            abstract = True
        
        def get_mugshot_url(self):
            """
            Returns the image containing the mugshot for the user.
    
            The mugshot can be a uploaded image or a Gravatar.
    
            Gravatar functionality will only be used when
            ``USERENA_MUGSHOT_GRAVATAR`` is set to ``True``.
    
            :return:
                ``None`` when Gravatar is not used and no default image is supplied
                by ``USERENA_MUGSHOT_DEFAULT``.
    
            """
            # First check for a mugshot and if any return that.
            if self.mugshot:
                return self.mugshot.url
    
            # Use Gravatar if the user wants to.
            if userena_settings.USERENA_MUGSHOT_GRAVATAR:
                return get_gravatar(self.user.email,
                                    userena_settings.USERENA_MUGSHOT_SIZE,
                                    userena_settings.USERENA_MUGSHOT_DEFAULT)
    
            # Gravatar not used, check for a default image.
            else:
                if userena_settings.USERENA_MUGSHOT_DEFAULT not in ['404', 'mm',
                                                                    'identicon',
                                                                    'monsterid',
                                                                    'wavatar']:
                    return userena_settings.USERENA_MUGSHOT_DEFAULT
                else: return None


class UserenaLanguageBaseProfile(UserenaBaseProfile):
    """
    Extends the :class:`UserenaBaseProfile` with a language choice.

    Use this model in combination with ``UserenaLocaleMiddleware`` automatically
    set the language of users when they are signed in.

    """
    language = models.CharField(_('language'),
                                max_length=5,
                                choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE[:2])

    class Meta:
        abstract = True
        permissions = PROFILE_PERMISSIONS

