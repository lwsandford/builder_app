# Generated by Django 4.2.3 on 2024-01-15 07:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contract_admin', '0008_remove_costing_committed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='committed_quotes',
            name='pdf',
            field=models.FileField(upload_to=''),
        ),
    ]
