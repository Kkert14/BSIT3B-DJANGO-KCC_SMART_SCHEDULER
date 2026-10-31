from django.db import models


ACCENT_PRESETS = [
    ('#2b8be6', 'Blue'),
    ('#6366f1', 'Indigo'),
    ('#7c3aed', 'Violet'),
    ('#1f9d63', 'Green'),
    ('#0d9488', 'Teal'),
    ('#d97706', 'Amber'),
    ('#e11d48', 'Rose'),
    ('#475569', 'Slate'),
]

FONT_STACKS = {
    'segoe': '"Segoe UI", system-ui, -apple-system, Arial, sans-serif',
    'inter': '"Inter", "Segoe UI", system-ui, sans-serif',
    'poppins': '"Poppins", "Segoe UI", system-ui, sans-serif',
    'system': 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
}

BRAND_ICONS = [
    ('fa-gear', 'Gear'),
    ('fa-calendar-days', 'Calendar'),
    ('fa-calendar-check', 'Calendar check'),
    ('fa-graduation-cap', 'Graduation cap'),
    ('fa-school', 'School'),
    ('fa-layer-group', 'Layers'),
    ('fa-table-columns', 'Timetable'),
    ('fa-clock', 'Clock'),
    ('fa-chalkboard-user', 'Chalkboard'),
    ('fa-book-open', 'Book'),
    ('fa-desktop', 'Monitor'),
    ('fa-bolt', 'Bolt'),
]

MAX_LOGO_BYTES = 2 * 1024 * 1024


def logo_suffix_for(head):
    """Return a safe extension for a supported logo image, or ''."""
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if head.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return '.webp'
    return ''


class AppearanceSettings(models.Model):
    """System-wide look and feel edited from the Settings page."""

    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]
    FONT_CHOICES = [
        ('segoe', 'Segoe UI'),
        ('inter', 'Inter'),
        ('poppins', 'Poppins'),
        ('system', 'System UI'),
    ]

    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')
    accent = models.CharField(max_length=7, default='#2b8be6')
    font = models.CharField(max_length=20, choices=FONT_CHOICES, default='segoe')
    brand_name = models.CharField(max_length=40, default='Smart Scheduler')
    brand_tagline = models.CharField(max_length=40, blank=True, default='Management System')
    brand_icon = models.CharField(max_length=40, default='fa-gear')
    logo = models.FileField(upload_to='brand/', blank=True)

    class Meta:
        db_table = 'appearance_settings'
        verbose_name = 'Appearance settings'
        verbose_name_plural = 'Appearance settings'

    def __str__(self):
        return 'Appearance settings'

    @classmethod
    def load(cls):
        """Return the single settings row without writing on every request."""
        return cls.objects.first() or cls()

    @property
    def accent_rgb(self):
        value = self.accent.lstrip('#')
        if len(value) != 6:
            return '43, 139, 230'
        try:
            channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
        except ValueError:
            return '43, 139, 230'
        return ', '.join(str(channel) for channel in channels)

    @property
    def font_stack(self):
        return FONT_STACKS.get(self.font, FONT_STACKS['segoe'])

    @property
    def brand_first(self):
        return (self.brand_name or '').split(' ', 1)[0]

    @property
    def brand_rest(self):
        parts = (self.brand_name or '').split(' ', 1)
        return parts[1] if len(parts) > 1 else ''

    @property
    def brand_icon_class(self):
        return self.brand_icon if self.brand_icon in dict(BRAND_ICONS) else 'fa-gear'

    @property
    def logo_url(self):
        return self.logo.url if self.logo else ''
