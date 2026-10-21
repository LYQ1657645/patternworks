from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('processing', '0006_job_cleanup_completed_at')]
    operations = [migrations.AddField(model_name='regexrule', name='columns', field=models.JSONField(default=list))]
