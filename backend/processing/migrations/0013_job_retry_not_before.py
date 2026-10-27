from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('processing', '0012_llmtransformation_input_tokens_and_more')]
    operations = [migrations.AddField(model_name='job', name='retry_not_before',
                                     field=models.DateTimeField(null=True, blank=True))]
