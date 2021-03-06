from django.conf.urls import patterns, url
from xbook.ajax import views

urlpatterns = [
    url(r"^u-(?P<uni>.*?)/prereq/(?P<code>.*?)$", views.subject_graph),
    url(r"^u-(?P<uni>.*?)/postreq/(?P<code>.*?)$", views.subject_graph, { "prereq": False }),

    url(r"^u-(?P<uni>.*?)/(?P<code>.*?)/details$", views.subject_details),

    url(r"^u-(?P<uni>.*?)/subject_list$", views.subject_list),

    url(r"subjects/(?P<subjectCode>.*?)/general_statistics", views.subject_statistics),
    url(r"subjects/(?P<subjectCode>.*?)/social_statistics", views.social_statistics),
    url(r"my_subjects/(?P<subjectCode>.*)", views.user_subject),

    url(r"^profile/(?P<username>.*?)/details$", views.profile_details),
    url(r"^profile/(?P<username>.*?)/?$", views.profile),
]
