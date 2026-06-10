# Kaiser's Detail Co. — Setup & Deployment Guide

This is a Python (Flask) app that serves your public website, handles online
bookings (one per day), and runs a password-protected admin panel.

```
kaiser-detail/
├── app.py                  # the server (public site + booking API + admin)
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html          # public website
│   ├── admin_login.html    # admin password page
│   └── admin.html          # admin dashboard
├── static/                 # your images go here (favicon, before/after, etc.)
├── deploy/
│   ├── kaiser.service      # systemd unit (keeps the app running)
│   └── nginx-kaiserdetailing.conf
└── bookings.db             # created automatically on first run (your live data)
```

---

## 1. Run it locally first (optional but recommended)

On your own computer, to make sure everything works before deploying:

```bash
cd kaiser-detail
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000 for the site, and http://localhost:8000/admin for
the admin panel (password: `Kaiser556!?!`).

Drop your images into the `static/` folder (see `static/PLACE_IMAGES_HERE.txt`
for the exact filenames the site expects).

---

## 2. Deploy on a Google Cloud VM

### 2a. Create the VM
In the Google Cloud Console → Compute Engine → VM instances → Create instance:
- A small machine (e2-small or e2-micro) is plenty.
- Boot disk: **Ubuntu 24.04 LTS**.
- Under **Firewall**, check **Allow HTTP traffic** and **Allow HTTPS traffic**.
- Create it, then note the VM's **external IP address**.

### 2b. Get your files onto the VM
SSH into the VM (the "SSH" button in the console works). Then either clone from
GitHub or upload the folder. Assuming a user named `kaiser`:

```bash
# on the VM
sudo apt update
sudo apt install -y python3-venv python3-pip nginx
# put the project at /home/kaiser/kaiser-detail (git clone or scp it up)
cd /home/kaiser/kaiser-detail
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> If your username isn't `kaiser`, update the paths and `User=` in
> `deploy/kaiser.service` and the `alias` path in the nginx config to match.

### 2c. Run the app as a service (so it stays up and restarts on reboot)

```bash
# pick a long random secret for sessions:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Edit `deploy/kaiser.service` and paste that value into `FLASK_SECRET`. Keep
`ADMIN_PASSWORD` as `Kaiser556!?!` or change it to something new. Then:

```bash
sudo cp deploy/kaiser.service /etc/systemd/system/kaiser.service
sudo systemctl daemon-reload
sudo systemctl enable --now kaiser
sudo systemctl status kaiser        # should say "active (running)"
```

The app now runs on 127.0.0.1:8000 (internal only — nginx puts it on the web).

### 2d. Put nginx in front

```bash
sudo cp deploy/nginx-kaiserdetailing.conf /etc/nginx/sites-available/kaiserdetailing
sudo ln -s /etc/nginx/sites-available/kaiserdetailing /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Visit `http://<your-VM-external-IP>/` — the site should load.

---

## 3. Point your domain at the VM

1. **Reserve a static IP** so it doesn't change: Google Cloud Console → VPC
   network → IP addresses → reserve the VM's external IP as static.
2. In your domain registrar's DNS settings for **kaiserdetailing.com**, create:
   - An `A` record: `@`  →  your VM's static IP
   - An `A` record: `www`  →  your VM's static IP
3. DNS can take a little while to propagate (minutes to a few hours).

---

## 4. Turn on HTTPS (free)

Once the domain points at the VM:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d kaiserdetailing.com -d www.kaiserdetailing.com
```

Follow the prompts. Certbot updates nginx to serve HTTPS and auto-renews the
certificate. Your site is now live at https://kaiserdetailing.com.

---

## 5. Day-to-day

- **Admin panel:** https://kaiserdetailing.com/admin  (password `Kaiser556!?!`)
  - See every booking: name, date, time, phone/email, service, add-ons,
    address, notes, and total.
  - Create a booking yourself with the "Create a Booking" button.
  - Delete a booking with its Delete button.
- **One booking per day** is enforced automatically — a day that's taken is
  blocked on the public calendar and rejected by the server even if two people
  try at once.

### Back up your bookings
Your data lives in `bookings.db`. To back it up:

```bash
cp /home/kaiser/kaiser-detail/bookings.db ~/bookings-backup-$(date +%F).db
```

### After changing any code
```bash
sudo systemctl restart kaiser
```

### Change the admin password later
Edit `ADMIN_PASSWORD` in `/etc/systemd/system/kaiser.service`, then:
```bash
sudo systemctl daemon-reload && sudo systemctl restart kaiser
```

---

## Notes & options

- **Email/text notifications:** the app records bookings but does not yet email
  or text you when one comes in. If you want that, a service like SendGrid
  (email) or Twilio (SMS) can be added — just ask.
- **Contact form:** the "Say Hello" form still posts to your Formspree endpoint,
  separate from the booking system. That's intentional — it's for general
  questions, not scheduling.
- **Security:** keep `FLASK_SECRET` private and consider changing the admin
  password from the default before going live.
