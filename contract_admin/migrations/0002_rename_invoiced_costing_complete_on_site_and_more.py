# Generated by Django 4.2.3 on 2023-12-20 06:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contract_admin', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='costing',
            old_name='invoiced',
            new_name='complete_on_site',
        ),
        migrations.RenameField(
            model_name='costing',
            old_name='prepayments',
            new_name='hc_next_claim',
        ),
        migrations.AddField(
            model_name='costing',
            name='hc_received',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='costing',
            name='notes',
            field=models.CharField(default=0, max_length=500),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='costing',
            name='qs_claimed',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='costing',
            name='sc_invoiced',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='costing',
            name='sc_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='costing',
            name='uncommitted',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
    ]
