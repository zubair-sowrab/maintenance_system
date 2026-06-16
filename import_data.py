import os, csv, django
# Tell the script where your project settings are
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tasks.models import MaintenanceWorkItem

def run_import():
    with open('import.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # get_or_create finds it if it exists, creates it if it doesn't
            obj, created = MaintenanceWorkItem.objects.get_or_create(
                project_type=row['project_type'],
                name_english=row['name_english'],
                name_arabic=row['name_arabic']
            )
            if created:
                print(f"Success: Added {row['name_english']}")
            else:
                print(f"Skipped: {row['name_english']} already exists")

if __name__ == "__main__":
    run_import()