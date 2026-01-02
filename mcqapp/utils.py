import pandas as pd
from .models import Subject, Question

def process_excel(file):
    df = pd.read_excel(file)
    for _, row in df.iterrows():
        subject, _ = Subject.objects.get_or_create(name=row['Subject'])
        
        options = {
            'A': row['Option A'],
            'B': row['Option B'],
            'C': row['Option C'],
            'D': row['Option D']
        }
        
        Question.objects.create(
            subject=subject,
            text=row['Question'],
            options=options,
            correct_answers=row['Correct Answer'],
            marks=row['Marks'],
            is_multi=',' in row['Correct Answer']
        )