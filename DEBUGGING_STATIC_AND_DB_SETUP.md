# Debugging Django Admin CSS and Production Database

This document is a step-by-step debug guide for the live site when:
- Django admin loads without CSS
- The production database does not contain movie and seat data

## 1. Confirm the problem

1. Open the live admin page.
2. Check the browser network tab for `/static/admin/...` requests.
3. If those requests return `404` or `500`, the admin CSS is not being served.

## 2. Confirm Django static settings

Open `bookmyseat/settings.py` and verify:
- `STATIC_URL = '/static/'`
- `STATIC_ROOT = BASE_DIR / 'staticfiles'`
- `STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'`
- `whitenoise.middleware.WhiteNoiseMiddleware` is present in `MIDDLEWARE`

This project is configured to collect static assets into `staticfiles` and serve them using WhiteNoise.

## 3. Confirm build / collected static files

Run locally from the project root:

```bash
python manage.py collectstatic --noinput
```

Then confirm the generated admin CSS exists:

```bash
ls staticfiles/admin/css
```

If the CSS files exist locally, the next step is verifying the deployment includes `staticfiles`.

## 4. Vercel deployment routing fix

In `vercel.json`, the deployment now includes an explicit static route:

```json
"routes": [
  {
    "src": "/static/(.*)",
    "dest": "/staticfiles/$1"
  }
]
```

This ensures requests on the live site for `/static/...` are mapped to the collected `staticfiles` directory.

## 5. Validate the deployed route

On the live site, open the same admin page and verify the browser network console again.

If `/static/admin/css/...` now returns `200`, the admin CSS problem is fixed.

## 6. Seed or add movie data

If the production DB is empty, populate it using one of these methods.

### 6.1 Seed sample movies

Run this on the live environment if you have terminal access:

```bash
python manage.py seed_movies
```

### 6.2 Add movies manually via Admin

Once admin CSS is restored, log in and add movies manually under the `Movies` section.

## 7. Additional debugging commands

If admin static files still fail, run:

```bash
python manage.py findstatic admin/css/login.css
```

Check whether Django can locate the admin CSS asset.

## 8. Common causes and fixes

- `collectstatic` not run during deployment
- `vercel.json` missing a `/static` route
- `STATIC_ROOT` set to `staticfiles` but static files not included in deployment bundle
- `DEBUG=False` on production while static routes are not configured correctly

## 9. Next steps after fix

1. Redeploy the site.
2. Re-open the admin page.
3. Verify the admin theme and login page CSS load properly.
4. Add or seed movie data.

---

If you want, I can also add a short `checklist` section into `README.md` so future deployments keep the same fix.