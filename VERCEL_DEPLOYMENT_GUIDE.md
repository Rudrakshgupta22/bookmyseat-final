# Vercel Serverless Deployment Guide

## Overview
This guide will help you deploy your Django BookMyShow clone application to Vercel using serverless functions.

## Prerequisites
- Vercel account (https://vercel.com)
- GitHub account
- Node.js installed locally (for Vercel CLI)
- Python 3.10 environment

## Step 1: Prepare Your Project for Vercel

### 1.1 Install Vercel CLI
```bash
npm install -g vercel
```

### 1.2 Login to Vercel
```bash
vercel login
```

### 1.3 Configure Environment Variables
Create environment variables in Vercel dashboard or using CLI:

**Required Environment Variables:**
```
DEBUG=False
SECRET_KEY=your-secret-key-here
DATABASE_URL=your-database-url-here
ALLOWED_HOSTS=your-app-name.vercel.app
CSRF_TRUSTED_ORIGINS=https://your-app-name.vercel.app
STRIPE_PUBLIC_KEY=your-stripe-public-key
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True
IS_VERCEL=True
```
> Note: `ALLOWED_HOSTS` must contain the hostname only, without `https://`. If you include the protocol, Django will reject the request with `Bad Request (400)`.

### 1.4 Update settings.py for Vercel
Your `bookmyseat/settings.py` should already be configured for Vercel with:
- Environment variable support
- Serverless detection (`IS_VERCEL`)
- Proper ALLOWED_HOSTS configuration

## Step 2: Deploy to Vercel

### 2.1 Initialize Vercel Project
```bash
vercel
```

Follow the prompts:
- Link to existing project or create new? → Create new
- Project name → bookmyseat-new
- Directory → ./

### 2.2 Configure Build Settings
Update `vercel.json` (already exists in your project):

```json
{
  "version": 2,
  "builds": [
    {
      "src": "bookmyseat/wsgi.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "50mb"
      }
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "bookmyseat/wsgi.py"
    }
  ],
  "functions": {
    "bookmyseat/wsgi.py": {
      "maxDuration": 30
    }
  }
}
```

### 2.3 Deploy
```bash
vercel --prod
```

## Step 3: Database Setup

### 3.1 Choose Database Provider
For production, use one of these:
- **PostgreSQL**: Recommended for production
- **Supabase**: Free tier available
- **ElephantSQL**: Managed PostgreSQL
- **Railway**: Modern cloud platform

### 3.2 Update DATABASE_URL
Set your production database URL in Vercel environment variables:
```
DATABASE_URL=postgresql://user:password@host:port/database
```

If you do not have a hosted database yet, the project can temporarily fall back to the checked-in `db.sqlite3` file on Vercel, but this is not recommended for long-term production use.

### 3.3 Run Migrations and Seed Data
After deployment, run migrations and seed the database:

```bash
# Run migrations (if needed)
python manage.py migrate

# Seed the database with your movie data
python manage.py seed_movies
```

**Note**: The seeding is now done manually to prevent startup issues. Run this command after your first deployment to populate movies.

## Step 4: Static Files & Media

### 4.1 Static Files
Django static files are served automatically by Vercel.

### 4.2 Media Files
For production, use cloud storage:
- **AWS S3**
- **Cloudinary**
- **Vercel Blob** (recommended)

Update your settings for media storage.

## Step 5: Email Configuration

### 5.1 Gmail Setup
1. Enable 2FA on Gmail
2. Generate App Password
3. Use App Password in EMAIL_HOST_PASSWORD

### 5.2 Alternative Providers
- **SendGrid**
- **Mailgun**
- **AWS SES**

## Step 6: Payment Integration (Stripe)

### 6.1 Stripe Setup
1. Create Stripe account
2. Get API keys from dashboard
3. Set webhook endpoint in Stripe
4. Configure webhook secret

### 6.2 Webhook URL
Set webhook URL to: `https://your-app-name.vercel.app/payments/webhook/`

## Step 7: Testing & Monitoring

### 7.1 Test Deployment
1. Check all pages load
2. Test user registration/login
3. Test movie booking flow
4. Test payment processing

### 7.2 Monitor Logs
```bash
vercel logs
```

### 7.3 Analytics
Use Vercel Analytics for performance monitoring.

## Step 8: Custom Domain (Optional)

### 8.1 Add Custom Domain
```bash
vercel domains add yourdomain.com
```

### 8.2 Update Environment Variables
Update ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS with your custom domain.

## Troubleshooting

### Common Issues:

1. **ModuleNotFoundError**: Check requirements.txt
2. **Database connection failed**: Verify DATABASE_URL
3. **Static files not loading**: Check STATIC_URL settings
4. **Email not sending**: Verify email credentials
5. **Payment failed**: Check Stripe configuration

### Debug Commands:
```bash
# Check Vercel deployment status
vercel ls

# View function logs
vercel logs --follow

# Redeploy
vercel --prod
```

## File Structure for Vercel
```
bookmyseat/
├── vercel.json          # Vercel configuration
├── requirements.txt     # Python dependencies
├── runtime.txt         # Python version (3.10.13)
├── bookmyseat/         # Django project
├── movies/             # Django app
├── users/              # Django app
└── templates/          # HTML templates
```

## Security Notes
- Never commit secrets to GitHub
- Use environment variables for all sensitive data
- Keep dependencies updated
- Monitor for security vulnerabilities

## Performance Optimization
- Use database indexes
- Implement caching
- Optimize images
- Use CDN for static files
- Monitor function execution time

---

**Happy Deploying! 🚀**