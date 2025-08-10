import time

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
from pay import Pay

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
            session['phone'] = phone
            session['organisation_id'] = organisation_id  # Store organisation_id in session
            flash('Welcome back!')
            return redirect(url_for('home'))

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
            return redirect(url_for('home'))

        verification = auth_manager.verify_otp(phone, otp)

        if verification:
            flash('Welcome! OTP verified successfully')
        else:
            flash('OTP verification failed, but continuing...')

        session.pop('phone', None)
        return redirect(url_for('home'))

    return render_template('index.html', phone=phone)


@app.route('/home')
def home():
    organisation_id = session['organisation_id']
    organisation_manager = Organisations()
    organisation_name, organisation_email = organisation_manager.get_organisational_name(organisation_id)

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


@app.route('/repayment_summary', methods=['GET'])
def repayment_summary():
    total = request.args.get('total', '0.00')
    loan_ids_string = request.args.get('loan_ids', '')
    month = request.args.get('month', '')

    # Default to current month if not provided
    if not month:
        month = datetime.now().strftime('%B')  # e.g., 'August'

    # Convert comma-separated string to list
    loan_ids = [id.strip() for id in loan_ids_string.split(',') if id.strip()]

    # Save to session
    session['checkout_month'] = month

    print(f"Total: {total}")
    print(f"Loan IDs: {loan_ids}")
    print(f"Month: {month}")

    return render_template('repayment_summary.html',
                           total=total,
                           loan_ids=loan_ids,
                           month=month)


@app.route('/checkout', methods=['POST', 'GET'])
def checkout():
    if request.method == 'POST':
        # This is when coming FROM repayment_summary.html
        total_amount = request.form.get('total_amount')
        transaction_fees = request.form.get('transaction_fees')
        loan_ids_str = request.form.get('loan_ids')
        month = session.get('checkout_month')  # Get from session

        # Convert loan_ids back to list if needed
        loan_ids = loan_ids_str.split(',') if loan_ids_str else []

        # Store checkout data in session for potential retries
        session['checkout_data'] = {
            'total_amount': total_amount,
            'transaction_fees': transaction_fees,
            'loan_ids_str': loan_ids_str,
            'month': month
        }

        # Render checkout.html with the data so user can enter contact details
        return render_template('checkout.html',
                               total=total_amount,
                               loan_ids=loan_ids,
                               month=month,
                               transaction_fees=transaction_fees)

    elif request.method == 'GET':
        # Handle GET requests - check if we have checkout data in session (for retries)
        checkout_data = session.get('checkout_data')

        if checkout_data:
            # User is coming back to retry payment
            loan_ids = checkout_data['loan_ids_str'].split(',') if checkout_data['loan_ids_str'] else []

            return render_template('checkout.html',
                                   total=checkout_data['total_amount'],
                                   loan_ids=loan_ids,
                                   month=checkout_data['month'],
                                   transaction_fees=checkout_data['transaction_fees'])
        else:
            # No checkout data available, redirect to home
            flash('No payment data available. Please select loans to pay for.', 'error')
            return redirect(url_for('home'))


@app.route('/pay', methods=['POST', 'GET'])
def pay():
    if request.method == 'POST':
        try:
            # Check if user is logged in
            organisation_id = session.get('organisation_id')
            if not organisation_id:
                flash('Session expired. Please login again.', 'error')
                return redirect(url_for('index'))

            # Get checkout data that was passed as hidden fields
            total_amount_str = request.form.get('total_amount', '0')
            transaction_fees_str = request.form.get('transaction_fees', '50')
            loan_ids_str = request.form.get('loan_ids', '')
            month = request.form.get('month', '')

            # Get user contact info from the form
            mobile_number = request.form.get('mobile_number', '').strip()
            email = request.form.get('email', '').strip()

            print(f"Debug - Received payment data:")
            print(f"  Total Amount: {total_amount_str}")
            print(f"  Transaction Fees: {transaction_fees_str}")
            print(f"  Loan IDs: {loan_ids_str}")
            print(f"  Month: {month}")
            print(f"  Mobile: {mobile_number}")
            print(f"  Email: {email}")

            # Server-side validation
            validation_errors = []

            # Validate required fields
            if not total_amount_str or total_amount_str == '0':
                validation_errors.append('Invalid payment amount')

            if not loan_ids_str:
                validation_errors.append('No loans selected for payment')

            if not month:
                validation_errors.append('Payment month not specified')

            if not mobile_number:
                validation_errors.append('Mobile number is required')

            # Validate email format if provided
            if email and '@' not in email:
                validation_errors.append('Please enter a valid email address')

            # If there are validation errors, redirect back to checkout with errors
            if validation_errors:
                for error in validation_errors:
                    flash(error, 'error')

                # Convert loan_ids back to list for template
                loan_ids = [id.strip() for id in loan_ids_str.split(',') if id.strip()]

                return render_template('checkout.html',
                                       total=total_amount_str,
                                       loan_ids=loan_ids,
                                       month=month,
                                       transaction_fees=transaction_fees_str)

            # Convert amounts to proper format
            try:
                total_amount_usd = float(total_amount_str)
                transaction_fees_usd = float(transaction_fees_str)
                total_amount_ngwee = int(total_amount_usd)
                transaction_fees_ngwee = int(transaction_fees_usd)
            except ValueError as e:
                flash('Invalid amount format', 'error')
                loan_ids = [id.strip() for id in loan_ids_str.split(',') if id.strip()]
                return render_template('checkout.html',
                                       total=total_amount_str,
                                       loan_ids=loan_ids,
                                       month=month,
                                       transaction_fees=transaction_fees_str)

            # Get organisation details
            organisation_manager = Organisations()
            org_data = organisation_manager.get_organisational_name(organisation_id)

            if isinstance(org_data, tuple):
                organisation_name, organisation_email = org_data
            else:
                organisation_name = 'organisation'
                organisation_email = email or "noreply@example.com"

            # Convert loan_ids back to list
            loan_ids = [id.strip() for id in loan_ids_str.split(',') if id.strip()]

            print(f"Debug - Processing {len(loan_ids)} loans: {loan_ids}")

            pay_manager = Pay()

            # Create description with all loan IDs
            loan_ids_display = ", ".join(loan_ids)

            print(f"Debug - Initiating payment:")
            print(f"  Mobile: {mobile_number}")
            print(f"  Amount: {total_amount_ngwee} ngwee")
            print(f"  Description: Loan repayment for {month}")

            try:
                # Make ONE payment for the total amount of ALL loans
                payment_response = pay_manager.initiate_payment(
                    number=mobile_number,
                    total_amount=total_amount_ngwee,
                    transaction_fees=transaction_fees_ngwee,
                    month=month,
                    loan_id=loan_ids_display,
                    organisation_name=organisation_name,
                    organisation_email=organisation_email or email or "noreply@example.com"
                )

                print(f"Debug - Payment response: {payment_response}")

                # Check if payment initiation was successful
                if 'error' in payment_response:
                    print(f"Payment initiation error: {payment_response['error']}")
                    # Keep checkout data in session so user can retry
                    session['checkout_data'] = {
                        'total_amount': total_amount_str,
                        'transaction_fees': transaction_fees_str,
                        'loan_ids_str': loan_ids_str,
                        'month': month
                    }
                    flash(f"Payment initiation failed: {payment_response.get('message', 'Unknown error')}", 'error')
                    return redirect(url_for('checkout'))

                # Extract payment ID correctly
                payment_data = payment_response.get('payment', {})
                payment_id = payment_data.get('id')

                if not payment_id:
                    print("No payment ID in response")
                    session['checkout_data'] = {
                        'total_amount': total_amount_str,
                        'transaction_fees': transaction_fees_str,
                        'loan_ids_str': loan_ids_str,
                        'month': month
                    }
                    flash('No payment ID received from gateway. Please try again.', 'error')
                    return redirect(url_for('checkout'))

                print(f"Debug - Payment initiated with ID: {payment_id}")

                # Clear checkout data from session since payment was successfully initiated
                session.pop('checkout_data', None)

                # Render loading page and then check status via JavaScript
                return render_template('payment_processing.html',
                                       payment_id=payment_id,
                                       loan_ids=loan_ids_str,
                                       total_amount=total_amount_str)

            except Exception as e:
                print(f"Payment initiation exception: {e}")
                # Keep checkout data in session so user can retry
                session['checkout_data'] = {
                    'total_amount': total_amount_str,
                    'transaction_fees': transaction_fees_str,
                    'loan_ids_str': loan_ids_str,
                    'month': month
                }
                flash(f'Payment processing error: {str(e)}', 'error')
                return redirect(url_for('checkout'))

        except Exception as e:
            print(f"Payment processing error: {e}")
            import traceback
            traceback.print_exc()
            flash('An error occurred during payment processing', 'error')
            return redirect(url_for('checkout'))

    else:
        # GET request - redirect to checkout
        return redirect(url_for('checkout'))


@app.route('/check_payment_status/<payment_id>', methods=['GET'])
def check_payment_status(payment_id):
    """AJAX endpoint to check payment status"""
    try:
        loan_ids_str = request.args.get('loan_ids', '')
        total_amount_str = request.args.get('total_amount', '0')

        pay_manager = Pay()
        payment_status_result = pay_manager.check_payment_status(payment_id)

        # Handle the new structured response
        if payment_status_result["status"] == "success":
            # Process loan repayments (existing logic)
            loan_ids = [id.strip() for id in loan_ids_str.split(',') if id.strip()]
            successful_loans = []
            failed_loans = []

            for loan_id in loan_ids:
                try:
                    repayment_response = pay_manager.record_repayment(loan_id)

                    if repayment_response.get('success'):
                        updated_payments_left, loans_data = pay_manager.reduce_remaining_payments(loan_id)

                        if updated_payments_left:
                            successful_loans.append({
                                'loan_id': loan_id,
                                'payment_id': payment_id
                            })
                        else:
                            failed_loans.append({
                                'loan_id': loan_id,
                                'error': 'Failed to update remaining payments'
                            })
                    else:
                        failed_loans.append({
                            'loan_id': loan_id,
                            'error': repayment_response.get('error', 'Failed to record repayment')
                        })

                except Exception as e:
                    failed_loans.append({
                        'loan_id': loan_id,
                        'error': str(e)
                    })

            return jsonify({
                'status': 'success',
                'successful_loans': successful_loans,
                'failed_loans': failed_loans,
                'payment_id': payment_id,
                'total_amount': total_amount_str
            })

        elif payment_status_result["status"] == "failed":
            # Payment was cancelled or failed - stop polling
            return jsonify({
                'status': 'failed',
                'reason': payment_status_result.get('reason', 'unknown'),
                'message': f'Payment was {payment_status_result.get("reason", "cancelled")}'
            })

        elif payment_status_result["status"] == "error":
            # API error - stop polling
            return jsonify({
                'status': 'error',
                'reason': payment_status_result.get('reason', 'unknown'),
                'message': 'Error checking payment status'
            })

        else:
            # Still pending
            return jsonify({
                'status': 'pending'
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        })



@app.route('/payment_result')
def payment_result():
    """Render final payment result page"""
    status = request.args.get('status', 'failed')
    payment_id = request.args.get('payment_id', '')
    total_amount = request.args.get('total_amount', '0')
    successful_loans = request.args.get('successful_loans', '[]')
    failed_loans = request.args.get('failed_loans', '[]')
    error = request.args.get('error', '')

    try:
        import json
        successful_loans = json.loads(successful_loans) if successful_loans != '[]' else []
        failed_loans = json.loads(failed_loans) if failed_loans != '[]' else []
    except:
        successful_loans = []
        failed_loans = []

    if status == 'success':
        if successful_loans and not failed_loans:
            return render_template('payment_success.html',
                                   successful_loans=successful_loans,
                                   payment_id=payment_id,
                                   total_amount=total_amount)
        elif successful_loans and failed_loans:
            return render_template('payment_partial.html',
                                   successful_loans=successful_loans,
                                   failed_loans=failed_loans,
                                   payment_id=payment_id,
                                   total_amount=total_amount)
        else:
            return render_template('payment_failed.html',
                                   error='Payment successful but failed to process loan records',
                                   failed_loans=failed_loans,
                                   payment_id=payment_id)
    else:
        return render_template('payment_failed.html',
                               error=error or 'Payment was not successful',
                               total_amount=total_amount)





if __name__ == '__main__':
    app.run(debug=True)