from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0002_employee_no_label'),
    ]

    operations = [
        migrations.RenameField(
            model_name='trainee',
            old_name='badge',
            new_name='emp_no',
        ),
        migrations.AlterField(
            model_name='trainee',
            name='emp_no',
            field=models.CharField(max_length=30, unique=True, verbose_name='Emp No.'),
        ),
    ]
