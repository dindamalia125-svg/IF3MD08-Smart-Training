from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_employee_no'),
    ]

    operations = [
        migrations.RenameField(
            model_name='user',
            old_name='employee_no',
            new_name='emp_no',
        ),
        migrations.AlterField(
            model_name='user',
            name='emp_no',
            field=models.CharField(blank=True, max_length=30, null=True, unique=True, verbose_name='Emp No.'),
        ),
    ]
