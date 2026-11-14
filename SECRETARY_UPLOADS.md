# Secretary image uploads

The app accepts independent Streamlit Secrets accounts with the `Secretary` rank. Add a dedicated account (use a unique, strong password) to the existing `[users]` secrets table:

```toml
[users.secretary]
password = "choose-a-unique-strong-password"
rank = "Secretary"
```

After saving secrets, restart the Streamlit app. Secretary accounts can access only **Secretary Uploads**. Admin accounts can access that page as well.

The upload page accepts JPG, PNG, and WebP files up to 10 MB each. Uploads are stored in the shared SQLite `image_uploads` table with their category, filename, uploader, and East Africa Time timestamp. The oven-temperature category is presented as the **Global oven-temperature image container**; HMI images are also retained in the shared archive.

**Number extraction is not implemented yet.** The current first step stores the source images and does not claim or write temperature values into production logs. The database includes a nullable `extracted_numbers` field for a future OCR/review workflow. The SQLite database currently lives alongside the app, following the existing persistence setup; deployments with ephemeral local storage need a persistent database volume before relying on long-term retention.
