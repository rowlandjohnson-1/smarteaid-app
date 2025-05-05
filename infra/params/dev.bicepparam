// infra/params/dev.bicepparam
using '../main.bicep'

parameters: {
  // companyPrefix: 'sdt' // Default in main.bicep
  // purpose: 'aidetector' // Default in main.bicep
  environment: 'dev'
  // location: 'uksouth' // Default in main.bicep

  // --- Container App --- 
  // REQUIRED: Specify the development container image (e.g., including 'dev' tag or similar)
  containerImage: '<your-acr-name>.azurecr.io/<your-image-name>:<your-dev-tag-or-latest>'
  // Defaults from main.bicep for dev are likely sufficient:
  // containerAppCpuCoreCount: '0.5'
  // containerAppMemoryGiB: '1.0Gi'
  // containerAppMinReplicas: 0
  // containerAppMaxReplicas: 2

  // --- Secrets --- 
  // REQUIRED: Provide development secret values here or via command-line/CI/CD
  cosmosDbConnectionString: '<COSMOS_DB_CONNECTION_STRING_DEV>'
  kindeClientSecret: '<KINDE_CLIENT_SECRET_DEV>'
  stripeSecretKey: '<STRIPE_SECRET_KEY_DEV_TEST>'
  storageConnectionString: '<AZURE_STORAGE_CONNECTION_STRING_DEV>'
}