from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('processing', '0005_job_attempt_count_job_attempt_token_job_heartbeat_at_and_more')]
    operations = [migrations.AddField(model_name='job', name='cleanup_completed_at',
                                     field=models.DateTimeField(blank=True, null=True))]
