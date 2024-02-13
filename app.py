import ssl
import socket
import models
import requests
import os
import msal
from email.message import EmailMessage

from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dateutil import parser as date_parser
from datetime import datetime, timedelta
from database import SessionLocal, engine
from sqlalchemy.orm import Session


models.Base.metadata.create_all(bind=engine)
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


# Helper function to access the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "show_error": True, "error_message": exc.detail},
    )


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    check_certs(SessionLocal())
    certificates = db.query(models.Certificates).all()

    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
            "certificates": certificates,
        },
    )


@app.post("/add")
def add(request: Request, common_name: str = Form(...), db: Session = Depends(get_db)):
    check_certs(SessionLocal())
    certificates = db.query(models.Certificates).all()

    try:
        cert = get_cert(common_name)
        not_before = cert.get("notBefore", None)
        not_after = cert.get("notAfter", None)
        cert_status = ""
        new_certificate = models.Certificates(
            common_name=common_name,
            not_before=not_before,
            not_after=not_after,
            cert_status=cert_status,
        )
    except HTTPException:
        return templates.TemplateResponse(
            "base.html",
            {"request": request, "show_error": True, "certificates": certificates},
        )

    db.add(new_certificate)
    db.commit()

    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@app.get("/delete/{cert_id}")
def delete(cert_id: int, db: Session = Depends(get_db)):
    certificate = (
        db.query(models.Certificates)
        .filter(models.Certificates.cert_id == cert_id)
        .first()
    )
    db.delete(certificate)
    db.commit()

    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@app.get("/email/{cert_id}")
def email(request: Request, cert_id: int, db: Session = Depends(get_db)):
    certificate = (
        db.query(models.Certificates)
        .filter(models.Certificates.cert_id == cert_id)
        .first()
    )

    send_email(certificate)

    certificates = db.query(models.Certificates).all()

    return templates.TemplateResponse(
        "base.html", {"request": request, "show_success": True, "certificates": certificates})


def check_certs(db: Session = Depends(get_db)):
    certificates = db.query(models.Certificates).all()

    for certificate in certificates:
        expiration_date = date_parser.parse(certificate.not_after).replace(tzinfo=None)
        thirty_days_from_now = datetime.now() + timedelta(days=30)

        if expiration_date <= thirty_days_from_now:
            certificate.cert_status = "Expiring"
        else:
            certificate.cert_status = "Valid"

    db.commit()
    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


def get_cert(url):
    try:
        # Create a socket connection to the host and port
        context = ssl.create_default_context()
        with socket.create_connection((url, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=url) as ssock:
                cert = ssock.getpeercert()
                return cert

    except socket.error as socket_error:
        raise HTTPException(
            status_code=400, detail="Invalid host: " + str(socket_error)
        )


def send_email(certificate):

    client_id = os.environ.get("DEVOPS_CLIENT_ID")
    client_secret = os.environ.get("DEVOPS_CLIENT_SECRET")
    client_tenant_id = os.environ.get("DEVOPS_TENANT_ID")

    authority_url = f"https://login.microsoftonline.com/{client_tenant_id}"
    scopes = ['https://graph.microsoft.com/.default']

    get_token = msal.ConfidentialClientApplication(
        client_id,
        authority=authority_url,
        client_credential=client_secret
    )

    token_result = get_token.acquire_token_for_client(scopes=scopes)
    access_token = token_result.get("access_token")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    email_message = EmailMessage()
    email_message["Subject"] = f"ITS - Certificate Notification | {certificate.common_name}"
    email_message["From"] = "devops@itsolutionsco.com"
    email_message["To"] = "helpdesk@itsolutionsco.com"

    payload = {
        "message": {
            "subject": email_message["Subject"],
            "body": {
                "contentType": "HTML",
                "content": f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Certification Notification</title>
                    </head>
                    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                    <table align="center"
                           style="background-color: #ffffff; border-radius: 5px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); margin: 0 auto;">
                        <tr>
                            <td style="padding: 20px; text-align: center;">
                                <h1 style="font-size: 24px; color: #333;">Certificate Notification</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px; text-align: center;">
                                <p style="font-size: 16px; color: #666;">This is a notification that the following certificate is expiring
                                    soon for:</p>
                                <p style="font-size: 16px; color: #666;"><strong>[ {certificate.common_name} ]</strong></p>
                                <p style="font-size: 16px; color: #666;">Created: {certificate.not_before}</p>
                                <p style="font-size: 16px; color: #666;">Expiring: {certificate.not_after}</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px; text-align: center;">
                                <a href="https://certs.itsolutionsco.com"
                                   style="background-color: #007BFF; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 5px; font-size: 16px;">View
                                    Certificate Dashboard</a>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px; text-align: center;">
                                <p style="font-size: 16px; color: #666;">Best,</p>
                                <p style="font-size: 16px; color: #666;"><strong>Dev Ops</strong></p>
                                <p style="font-size: 16px; color: #666;">Information Technology Solutions</p>
                            </td>
                        </tr>
                    </table>
                    </body>
                    </html>
                """,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": email_message["To"],
                    },
                },
            ],
        }
    }

    endpoint = f'https://graph.microsoft.com/v1.0/users/{email_message["From"]}/sendMail'
    post = requests.post(endpoint, headers=headers, json=payload)
    post.raise_for_status()
