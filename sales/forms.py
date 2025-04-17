from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.forms import ClearableFileInput
from django import forms

from .models import Table, Sale, Business, SubscriptionPlan, UserProfile
from .utils import convert_currency

class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['item', 'quantity', 'total_amount', 'table', 'status', 'payment_mode']


class BusinessRegistrationForm(forms.ModelForm):
    subscription_expiry = forms.DateTimeField(disabled=True, required=False)
    currency = forms.ChoiceField(
        choices=[('USD', 'USD'), ('EUR', 'EUR'), ('Ksh', 'Ksh')],  # Example currencies
        required=True,
    )
    converted_amount = forms.DecimalField(label="Converted Amount (in selected currency)", required=False, disabled=True)
    
    class Meta:
        model = Business
        fields = ['name', 'subscription_plan', 'logo', 'currency', 'subscription_expiry', 'is_active']
        
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Business Name'}),
            'subscription_plan': forms.Select(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'currency': forms.NumberInput(attrs={'placeholder': 'Currency'}),
            'subscription_expiry': forms.DateInput(attrs={'placeholder': 'Subscription expiry'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("Queryset in Form:", SubscriptionPlan.objects.all())
        self.fields['subscription_plan'].queryset = SubscriptionPlan.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        subscription_plan = cleaned_data.get('subscription_plan')
        currency = cleaned_data.get('currency')

        if subscription_plan and currency:
            amount_in_usd = subscription_plan.amount
            converted = convert_currency(amount_in_usd, 'USD', currency)
            if converted is None:
                raise forms.ValidationError("Could not fetch conversion rates. Try again later.")
            cleaned_data['converted_amount'] = converted
        return cleaned_data


class UserRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}))
    profile_picture = forms.ImageField(required=False, widget=ClearableFileInput(attrs={'class': 'form-control-file'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'password']

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        print("Initializing UserRegistrationForm:", self.fields)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            if not username.endswith('@digiserve'):
                username += '@digiserve'
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])

        # If a profile picture is uploaded, save it to the user's profile
        profile_picture = self.cleaned_data.get('profile_picture')
        print(f"Profile Picture: {profile_picture}")  # Ensure the file is being passed correctly

        if profile_picture:
            user.profile_picture = profile_picture

        # Save the user first to ensure it's in the database
        if commit:
            user.save()
            if profile_picture:
                # Save the profile picture to the UserProfile
                user.profile.profile_picture = profile_picture
                user.profile.save()

        if self.business:
            self.business.users.add(user)
            
        return user
        

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'email': forms.EmailInput(attrs={'readonly': 'readonly'}),  # Email shouldn't be editable
        }


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Old Password'}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'New Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm New Password'}))

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', "New passwords do not match.")
        return cleaned_data


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username and not username.endswith('@digiserve'):
            username += '@digiserve'
        return username


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ['username', 'email']
        

class EditUserForm(forms.ModelForm):
    profile_picture = forms.ImageField(
        required=False,
        label="Profile Picture",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control-file'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username']

    def save(self, commit=True):
        user = super().save(commit=False)
        profile_picture = self.cleaned_data.get('profile_picture')

        if commit:
            user.save()
            if profile_picture:
                if not hasattr(user, 'profile'):
                    UserProfile.objects.create(user=user)  # Ensure profile exists
                user.profile.profile_picture = profile_picture
                user.profile.save()

        return user
