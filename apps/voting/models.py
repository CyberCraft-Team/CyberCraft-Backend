from django.db import models
from django.conf import settings


class VotingSite(models.Model):
    name = models.CharField(max_length=100)
    url = models.URLField()
    bonus = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "voting_sites"
        verbose_name = "Voting Site"
        verbose_name_plural = "Voting Sites"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Vote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="votes"
    )
    site = models.ForeignKey(VotingSite, on_delete=models.CASCADE, related_name="votes")
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "votes"
        verbose_name = "Vote"
        verbose_name_plural = "Votes"

    def __str__(self):
        return f"{self.user.username} - {self.site.name}"
