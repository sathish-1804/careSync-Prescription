from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_migrate import Migrate
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import urllib

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+mysqlconnector://{os.environ.get('DB_USER')}:{os.environ.get('DB_PASSWORD')}@{os.environ.get('HOST_NAME')}/{os.environ.get('DB_NAME')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Initialize Flask-Migrate
CORS(app)

# Azure Blob Storage configuration
connection_str = os.environ["AZURE_CONNECTION_STR"]
container_name = 'storage-container'
blob_service_client = BlobServiceClient.from_connection_string(conn_str=connection_str)

# Define the User model
class User(db.Model):
    __tablename__ = 'Users'
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    user_details = db.Column(db.Boolean, default=False)

class Prescription(db.Model):
    __tablename__ = 'Prescriptions'
    prescription_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id', ondelete='CASCADE'), nullable=False)
    clinic_name = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.Date, nullable=False)
    file_link = db.Column(db.Text, nullable=False)


def upload_file_and_get_url(file):
    try:
        filename = file.filename
        encoded_filename = urllib.parse.quote(filename)

        # Get a container client
        container_client = blob_service_client.get_container_client(container=container_name)

        # Upload the file
        container_client.upload_blob(name=filename, data=file, overwrite=True)

        # Generate a SAS token for the uploaded blob
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=filename,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1)  # Token valid for 1 hour
        )

        # Construct the URL of the blob including the SAS token
        blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{encoded_filename}?{sas_token}"

        return blob_url
    except Exception as e:
        print(f"Error uploading file: {e}")  # Add this line for debugging
        raise



@app.route('/upload_prescription', methods=['POST'])
def upload_prescription():
    try:
        user_id = request.form['user_id']
        clinic_name = request.form['clinic_name']
        description = request.form['description']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        file = request.files['file']
        file_link = upload_file_and_get_url(file)

        new_prescription = Prescription(
            user_id=user_id,
            clinic_name=clinic_name,
            description=description,
            filename=file.filename,
            date=date,
            file_link=file_link
        )
        db.session.add(new_prescription)
        db.session.commit()

        response = {"message": "Prescription uploaded successfully", "file_link": file_link}
        print(response)
        return jsonify(response), 201
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/get_prescriptions/<user_id>', methods=['GET'])
def get_prescriptions(user_id):

    prescriptions = Prescription.query.filter_by(user_id=user_id).all()
    output = []
    for prescription in prescriptions:
        output.append({
            'prescription_id': prescription.prescription_id,
            'user_id': prescription.user_id,
            'clinic_name': prescription.clinic_name,
            'filename': prescription.filename,
            'description': prescription.description,
            'date': prescription.date.isoformat(),
            'file_link': prescription.file_link
        })
    return jsonify(output)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
