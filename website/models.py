# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.exceptions import ValidationError      # Needed for clean validations i.e Category
from django.db import models                            # Brings in models concept
from django.db import transaction                       # Needed for save overide
from django.db.models import F                          # Needed for math
from django.db.models import Q, UniqueConstraint        # Needed to limit logging run id value
from django.utils import timezone                       # needed for time delta 

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
    bluesky         = models.CharField(max_length=256,blank=False,null=False,help_text="Bluesky Handle incl @", verbose_name="Bluesky")
    modifier        = models.FloatField(default=2, blank=False, help_text="Rank Modifier", verbose_name="Modifier Value")
    last_article    = models.IntegerField(default=0, help_text="Days since last article", verbose_name="Last Article")
    batch_num       = models.IntegerField(default=0, help_text="Ingest Batch Number", verbose_name="Batch Number")
    #default_image  = models.
    hidden          = models.BooleanField(default=False, help_text="Is this site hidden?", verbose_name="Site Hidden")
    load_error      = models.BooleanField(default=False, help_text="Has this site had a load error?", verbose_name="Load Error")
    description     = models.TextField(max_length=2000, blank=False,null=False,help_text="Explanation of the site", verbose_name="Site Description")
    # Metadata
    class Meta:
        db_table = "sites"
        ordering = ['name']
        verbose_name = "Sites"
        verbose_name_plural = "Sites"
        constraints = [models.UniqueConstraint(fields=["url"], name='unique_site_url')]
        #indexes = [] #come back to this
    # Methods
    def clean(self):
        super().clean()
        # Ensure tags belong to the selected category
        if not self.pk:  # Skip validation if the instance is not saved yet
            return
        if self.category:
            invalid_tags = self.tags.exclude(parent=self.category)
            if invalid_tags.exists():
                raise ValidationError({
                    'tags': f"The following tags are not under the selected category '{self.category}': {', '.join(tag.value for tag in invalid_tags)}"
                })

    def save(self, *args, **kwargs):
        # Save the instance first to ensure it has an ID
        if not self.pk:
            super().save(*args, **kwargs)  # Save the instance to generate the ID
        else:
            with transaction.atomic():
                super().save(*args, **kwargs)  # Save the instance again if needed

    def __str__(self):
        return self.name

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Articles 
# ===== ===== ===== ===== ===== ===== ===== =====
class Articles(models.Model):
    # Fields
    title       = models.CharField(max_length=256,blank=False,null=False,help_text="", verbose_name="Article Title")
    url         = models.URLField(blank=False,null=False, help_text="", verbose_name="Article URL")
    image_url   = models.CharField(max_length=512,blank=False,null=False,help_text="", verbose_name="Image Reference")
    site        = models.ForeignKey(Sites, on_delete=models.CASCADE)
    published   = models.DateField(null=True, blank=True, help_text="The date the article was published", verbose_name="Published Date")
    created     = models.DateTimeField(auto_now_add=True,null=True, blank=True, help_text="The date the article was created in the site", verbose_name="Created Date") 
    run_id      = models.IntegerField(default=0, help_text="The id of the run that this article was part of", verbose_name="Run Id")
    boost       = models.FloatField(default=0,blank=False,help_text="Boosts the article artificially",verbose_name="Boost Count")
    clicks      = models.FloatField(default=0,blank=False,help_text="Count of link clicks",verbose_name="Click Count")
    modifier    = models.FloatField(default=1,blank=False,help_text="",verbose_name="Modifier Score")
    rank        = models.GeneratedField(
                    expression=((F("clicks")+ F("boost")) * F("modifier")),
                    output_field=models.IntegerField(default=0,blank=False,help_text="Rank in the feed", verbose_name="Rank Score"),
                    db_persist=True,
                )
    hidden      = models.BooleanField(default=False, help_text="The article is hidden", verbose_name="Article Hidden")
    site_hide   = models.BooleanField(default=False, help_text="The parent site is hidden", verbose_name="Site Hidden")
    bluesky     = models.BooleanField(default=False, help_text="The article has been posted to Bluesky", verbose_name="Article Posted to Bluesky")
    # Metadata
    class Meta:
        db_table = "articles"
        ordering = ['created']
        verbose_name = "Articles"
        verbose_name_plural = "Articles"
        constraints = [models.UniqueConstraint(fields=["url"], name='unique_url')]
        #indexes = [] # come back to this
    # Methods 
    def __str__(self):
        return self.title
    
# ===== ===== ===== ===== ===== ===== ===== ===== 
# Logging
# ===== ===== ===== ===== ===== ===== ===== =====
class Logging(models.Model):
    # Drop down selection
    LOG_CHOICES = [
        ('INGEST_COMPLETE','Ingest Complete'),
        ('INGEST_ERROR', 'Ingest Error'),
        ('INGEST_RUN_ID', 'Ingest Run Number'),
        ('AGE_TASK', 'Age Task Result'),
        ('BATCH_TASK', 'Batch Sites Task Result'),
        ('HIDE_ARTICLES_TASK', 'Hide Articles Task Result'),
        ('HIDE_SITES_TASK', 'Hide Sites Task Result'),
        ('LAST_ARTICLE_TASK', 'Last Articles Task Result'),
        ('FILTER_ARTICLE_TASK', 'Filter Articles Task Result'),
    ]
    # Fields
    log_type = models.CharField(max_length=20, choices=LOG_CHOICES, help_text="Category of Log", verbose_name="Log Type")
    created  = models.DateTimeField(auto_now_add=True, null=True, blank=True, help_text="The date the log occured", verbose_name="Created Date")
    value    = models.TextField(max_length=9000, blank=False, null=False, help_text="Value of the log", verbose_name="Logging Output")
    # Metadata
    class Meta:
        db_table = "logging"
        ordering = ['created']
        verbose_name = "Logging"
        verbose_name_plural = "Logging"
        constraints = [
            # Partial unique index: only enforces uniqueness when log_type == 'INGEST_RUN_ID'
            UniqueConstraint(
                fields=['log_type'],
                condition=Q(log_type='INGEST_RUN_ID'),
                name='unique_ingest_run_id'
            )
        ]
    # Methods 
    def __str__(self):
        return self.log_type
    

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Clicks
# ===== ===== ===== ===== ===== ===== ===== =====
#
# Revisit this!
#
class Clicks(models.Model):
    # Fields
    article     = models.CharField(max_length=128,blank=False,null=False,help_text="", verbose_name="Article ID")
    session     = models.CharField(max_length=128,blank=False,null=False,help_text="", verbose_name="Session ID")
    date        = models.DateField(default=timezone.now,help_text="",verbose_name="Vote Date")
    # Metadata
    class Meta:
        db_table = "clicks"
        ordering = ['session']
        verbose_name = "Clicks"
        verbose_name_plural = "Clicks"
        indexes = [
            models.Index(fields=['session','article'], name='vote_exists_idx'),
        ]
    # Methods 
    def __str__(self):
        return str(self.pk)