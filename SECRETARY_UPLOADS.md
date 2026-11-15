# Karani image uploads

The app accepts independent Streamlit Secrets accounts with the `Secretary` rank. Add a dedicated account to the existing `[users]` secrets table (choose a unique, strong password):

```toml
[users.Karani]
password = "choose-a-unique-strong-password"
rank = "Secretary"
```

After saving secrets, restart the Streamlit app. The `Karani` account can access **Karani Uploads** and **Paper ID**. Admin accounts can access Karani Uploads as well. Usernames are case-insensitive for sign-in, and the app loads accounts dynamically from the `[users]` table.

The upload page accepts JPG, PNG, and WebP files up to 10 MB each. Uploads are stored in the shared SQLite `image_uploads` table with their category, filename, uploader, and East Africa Time timestamp. The oven-temperature category is presented as the **Global oven-temperature image container**; HMI images are also retained in the shared archive.

Oven images are OCR-processed into hourly readings when six values are detected. The SQLite database currently lives alongside the app; deployments with ephemeral local storage need a persistent database volume before relying on long-term retention.
