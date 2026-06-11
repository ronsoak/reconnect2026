# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.db import models
from django.core.exceptions import ValidationError

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Website Logic Model
# ===== ===== ===== ===== ===== ===== ===== ===== 
class Logic(models.Model):
    # Drop down selection
    LOGIC_CHOICES= [
        ('KEYWORD','Keyword'),
        ('CATEGORY', 'Category'),
        ('TAG', 'Tag'),
        ('SITE_TYPE','Type')
    ]
    # Fields
    logic_type  = models.CharField(max_length=20, choices=LOGIC_CHOICES, help_text="Category of Logic", verbose_name="Logic Type")
    parent      = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE,related_name='children',limit_choices_to={'logic_type': 'CATEGORY'}, help_text="What category does this tag belog to", verbose_name="Parent Category")
    value       = models.CharField(max_length=512,blank=False,null=False,help_text="Logic Value", verbose_name="Value") 
    # Metadata
    class Meta:
        unique_together = ('value', 'parent')  # Allow same name under different parents
        db_table = "logic"
        ordering = ['logic_type']
        verbose_name = "Logic"
        verbose_name_plural = "Logic"
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.value} > {self.value}"
        return self.value

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Sites 
# ===== ===== ===== ===== ===== ===== ===== =====
class Sites(models.Model):
    # Fields 
    name            = models.CharField(max_length=256,blank=False,null=False,help_text="Name of the Site", verbose_name="Name")
    url             = models.URLField(blank=False,null=False, help_text="Top level URL of the Site", verbose_name="Site URL")
    rss_feed        = models.URLField(blank=False,null=False, help_text="The URL of the Feed", verbose_name="Feed URL")
    site_type       = models.ForeignKey('Logic', on_delete=models.CASCADE, limit_choices_to={'logic_type': 'SITE_TYPE'}, related_name='site_type', verbose_name="Type", help_text="Select a type for this site",  null=True)
    category        = models.ForeignKey('Logic', on_delete=models.CASCADE, limit_choices_to={'logic_type': 'CATEGORY'}, related_name='site_category', verbose_name="Category", help_text="Select a category for this site")
    tags            = models.ManyToManyField('Logic',limit_choices_to={'logic_type': 'TAG'},related_name='site_tag',verbose_name="Tags",help_text="Select tags for this site")
    bluesky         = models.CharField(max_length=256,blank=False,null=False,help_text="Bluesky Handle", verbose_name="Bluesky")
    modifier        = models.FloatField(default=2, blank=False, help_text="Rank Modifier", verbose_name="Modifier Value")
    last_article    = models.IntegerField(default=0, help_text="Days since last article", verbose_name="Last Article")
    #default_image  = models.
    hidden          = models.BooleanField(default=False, help_text="Is this site hidden?", verbose_name="Site Hidden")
    rss_error       = models.BooleanField(default=False, help_text="Has this site had RSS issues?", verbose_name="RSS Error")
    description     = models.TextField(max_length=2000, blank=False,null=False,help_text="Explanation of the site", verbose_name="Site Description")
    # Metadata
    class Meta:
        db_table = "sites"
        ordering = ['name']
        verbose_name = "Sites"
        verbose_name_plural = "Sites"
        constraints = [models.UniqueConstraint(fields=["url"], name='unique_site_url')]
        indexes = [ # come back to this
            models.Index(fields=['hidden'], name='hidden_site_idx'),
            models.Index(fields=['url'], name='url_idx')
        ]
    # Methods
    def clean(self):
        super().clean()
        # Ensure tags belong to the selected category
        if self.category:
            invalid_tags = self.tags.exclude(parent=self.category)
            if invalid_tags.exists():
                raise ValidationError({
                    'tags': f"The following tags are not under the selected category '{self.category}': {', '.join(tag.value for tag in invalid_tags)}"
                })
    def __str__(self):
        return self.name

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Articles 
# ===== ===== ===== ===== ===== ===== ===== =====