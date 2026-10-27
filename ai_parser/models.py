from django.db import models


class Manpower(models.Model):
    # Use this model only if STA does not already have a Manpower/Employee model.
    employee_number = models.CharField(max_length=30, unique=True, db_index=True)
    employee_name = models.CharField(max_length=180)
    doc = models.DateField(null=True, blank=True)
    position = models.CharField(max_length=120, blank=True)
    section_code = models.CharField(max_length=10, default="2700", editable=False)
    section = models.CharField(max_length=50, default="Haemo", editable=False)
    supervisor = models.CharField(max_length=120, blank=True)
    shift = models.CharField(max_length=50, blank=True, default="Normal")
    status = models.CharField(max_length=80, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "manpower"
        ordering = ["employee_number"]

    def __str__(self):
        return f"{self.employee_number} - {self.employee_name}"
