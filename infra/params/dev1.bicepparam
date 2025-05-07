// infra/params/dev1.bicepparam
// Parameters for the new 'dev1' environment, targeting resource group 'rg-sdt-uks-aidetector-dev1'
using '../main.bicep' // Assuming main.bicep is in the parent directory (e.g., ./infra/main.bicep)

parameters: {
  // companyPrefix: 'sdt' // Default in main.bicep
  // purpose: 'aidetector' // Default in main.bicep
  environment: 'dev1' // <<< CHANGED: This will result in rgName 'rg-sdt-uks-aidetector-dev1'
  // location: 'uksouth' // Default in main.bicep

  // --- Container App ---
  // REQUIRED: Specify the development container image (e.g., including 'dev1' tag or your latest SHA)
  // This image MUST have your FastAPI application with /healthz and /readyz endpoints.
  containerImage: 'acrsdtaidetectordev.azurecr.io/backend-api:latest' // Replace with your actual image and tag for dev1

  // Defaults from main.bicep for non-prod are likely sufficient:
  // containerAppCpuCoreCount: '0.5'
  // containerAppMemoryGiB: '1.0Gi'
  // containerAppMinReplicas: 1 // Defaults to 1 for non-prod in main.bicep
  // containerAppMaxReplicas: 2

  // --- Secrets ---
  // REQUIRED: Provide 'dev1' specific secret values here or ensure they are passed
  // securely via your CI/CD pipeline (e.g., as overrides to the az deployment sub create command).
  mongoDbUrl: '<YOUR_DEV1_MONGODB_CONNECTION_STRING>'
  kindeClientSecret: '<YOUR_DEV1_KINDE_CLIENT_SECRET>'
  stripeSecretKey: '<YOUR_DEV1_STRIPE_SECRET_KEY_TEST_MODE>'
  storageConnectionString: '<YOUR_DEV1_AZURE_STORAGE_CONNECTION_STRING>'

  // --- Kinde Non-Secrets ---
  // REQUIRED: Provide these values for your 'dev1' Kinde setup.
  kindeDomain: 'https://<your_kinde_subdomain_for_dev1>.kinde.com' // Replace
  kindeAudience: '<your_kinde_api_audience_for_dev1>' // Replace
}