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
from loans import Loans
from organisation import Organisations

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
        print(phone)

        # Verify number in database
        phone_status, organisation_id = auth_manager.check_organisation_number(phone)

        if not phone_status:
            flash('Number is not registered with any organisation')
        else:
            # Send OTP after confirming phone is in database
            otp_sent = auth_manager.send_otp(phone)
            if otp_sent:
                session['phone'] = phone
                session['organisation_id'] = organisation_id  # Store organisation_id in session
                flash('OTP sent to your phone')
                return redirect(url_for('otp_verification'))
            else:
                flash('Failed to send OTP. Please try again.')

    return render_template('index.html')



@app.route('/otp_verification', methods=['GET', 'POST'])
def otp_verification():
    auth_manager = UserAuthentication()
    phone = session.get('phone')

    if not phone:
        flash('Session expired or invalid access')
        return redirect(url_for('index'))

    if request.method == 'POST':
        otp = request.form.get('otp')

        if not otp:
            flash('Please enter the OTP')
            return render_template('index.html', phone=phone)

        verification = auth_manager.verify_otp(phone, otp)

        if verification:
            flash('Welcome! OTP verified successfully')
            session.pop('phone', None)
            return redirect(url_for('home'))
        else:
            flash('Invalid OTP. Please try again.')
            return render_template('index.html', phone=phone)

    # GET request - show the OTP modal by passing phone to template
    return render_template('index.html', phone=phone)

@app.route('/home')
def home():
    organisation_id = session['organisation_id']
    organisation_manager = Organisations()
    organisation_name = organisation_manager.get_organisational_name(organisation_id)

    return render_template('home.html', organisation_name = organisation_name)


@app.route('/monthly_payment_schedules')
def monthly_payment_schedules():
    loans_manager = Loans()
    organisation_id = session['organisation_id']

    schedule_data = loans_manager.get_monthly_payment_schedules_for_template(organisation_id)

    return render_template('monthly_payment_schedules.html', schedule_data=schedule_data)


@app.route('/staff_breakdown/<month>')
def monthly_payment_details(month):
    loans_manager = Loans()
    organisation_id = session['organisation_id']

    # Get all borrowers for this specific month
    borrowers_data = loans_manager.get_borrower_payment_details_for_month(organisation_id, month)

    # Format month for display
    month_display = loans_manager._format_month_display(month)

    return render_template('staff_breakdown.html',
                           borrowers_data=borrowers_data,
                           month=month,
                           month_display=month_display)


@app.route('/repayment_summary/<total>/loan_ids=[]', methods=['POST','GET'])
@app.route('/repayment_summary', methods=['GET'])
def repayment_summary():
    total = request.args.get('total', '0.00')
    loan_ids_string = request.args.get('loan_ids', '')
    month = request.args.get('month', '')

    # Convert comma-separated string to list
    loan_ids = [id.strip() for id in loan_ids_string.split(',') if id.strip()]

    print(f"Total: {total}")
    print(f"Loan IDs: {loan_ids}")
    print(f"Month: {month}")

    # You can now use these loan_ids to fetch additional borrower details
    # from your database if needed for the summary page

    return render_template('repayment_summary.html',
                           total=total,
                           loan_ids=loan_ids,
                           month=month)


if __name__ == '__main__':
    app.run(debug=True)