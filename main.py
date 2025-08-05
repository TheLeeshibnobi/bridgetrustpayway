from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect, generate_csrf

import os
from datetime import datetime
import traceback
import secrets
import io
import pandas as pd

# Load environment variables
load_dotenv()

# modules
from auth import UserAuthentication

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY') or 'fallback-secret-key-for-development'
csrf = CSRFProtect(app)


# Make CSRF token available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())


@app.route('/', methods=['POST', 'GET'])
def index():
    auth_manager = UserAuthentication()

    if request.method == 'POST':
        phone = request.form.get('phone')

        # Verify number in database
        phone_result = auth_manager.check_organisation_number(phone)
        if not phone_result:
            flash('Number is not registered with any organisation')
        else:
            session['phone'] = phone
            return redirect(url_for('otp_verification'))

    return render_template('index.html')


@app.route('/otp_verification', methods=['GET', 'POST'])
def otp_verification():
    auth_manager = UserAuthentication()
    phone = session.get('phone')

    otp = request.form.get('otp')

    if not phone:
        flash('Session expired or invalid access')
        return redirect(url_for('index'))

    verification = auth_manager.verify_otp(phone, otp)

    if not verification:
        flash('invalid otp')

    flash('welcome')


    # Proceed with OTP logic
    return render_template('home.html')


if __name__ == '__main__':
    app.run(debug=True)