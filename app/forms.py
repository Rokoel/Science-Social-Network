from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, BooleanField, SelectField, DateTimeField, DateField, TimeField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from app.models import User, Project

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    name = StringField('Name', validators=[DataRequired()])
    surname = StringField('Surname', validators=[DataRequired()])
    family_name = StringField('Family Name')
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    name = StringField('Name', validators=[DataRequired()])
    surname = StringField('Surname', validators=[DataRequired()])
    family_name = StringField('Family Name')
    skills = TextAreaField('Skills')
    university = StringField('University')
    degree = StringField('Degree')
    fields_interests = TextAreaField('Fields/Interests')
    avatar = FileField('Avatar', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Save Changes')
    
    def __init__(self, original_username, original_email, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email
        
    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')
                
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('Please use a different email address.')

class ProjectForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    goals = TextAreaField('Goals', validators=[DataRequired()])
    deadline_date = DateField('Deadline Date', format='%d/%m/%Y', validators=[DataRequired()])
    deadline_time = TimeField('Deadline Time (Optional, 24hr format HH:MM)', format='%H:%M', validators=[Optional()])
    project_type_choices = [
        ("Project", "Project"),
        ("Experiment", "Experiment"),
        ("Study", "Study"),
        ("Other", "Other"),
    ]
    project_type = SelectField(
        "Project Type",
        choices=project_type_choices,
        validators=[DataRequired()],
    )
    is_public = BooleanField('Public Project', default=True)
    submit = SubmitField('Create Project')

class EditProjectForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    goals = TextAreaField('Goals', validators=[DataRequired()])
    deadline_date = DateField('Deadline Date', format='%d/%m/%Y', validators=[DataRequired()])
    deadline_time = TimeField('Deadline Time (Optional, 24hr format HH:MM)', format='%H:%M', validators=[Optional()])
    project_type_choices = [
        ("Project", "Project"),
        ("Experiment", "Experiment"),
        ("Study", "Study"),
        ("Other", "Other"),
    ]
    project_type = SelectField(
        "Project Type",
        choices=project_type_choices,
        validators=[DataRequired()],
    )
    is_public = BooleanField('Public Project')
    submit = SubmitField('Save Changes')

    def __init__(self, original_title, *args, **kwargs):
        super(EditProjectForm, self).__init__(*args, **kwargs)
        self.original_title = original_title

    def validate_title(self, title):
        if title.data != self.original_title:
            project = Project.query.filter_by(title=title.data).first()
            if project:
                raise ValidationError('That project title is already in use. Please choose a different one.')


class MessageForm(FlaskForm):
    text = TextAreaField("Message") # Removed DataRequired
    file = FileField(
        "File",
        validators=[
            FileAllowed(["jpg", "png", "jpeg", "pdf", "doc", "docx", "txt"]),
            Optional(), # File is optional
        ],
    )
    submit = SubmitField("Send")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if not self.text.data and not self.file.data:
            msg = "Either text or a file is required."
            self.text.errors.append(msg)
            self.file.errors.append(msg)
            return False
        return True

class ChatForm(FlaskForm):
    name = StringField('Chat Name', validators=[DataRequired()])
    submit = SubmitField('Create Chat')

class SearchForm(FlaskForm):
    query = StringField('Search', validators=[DataRequired()])
    search_type = SelectField('Type', choices=[('projects', 'Projects'), ('chats', 'Chats')])
    submit = SubmitField('Search')
