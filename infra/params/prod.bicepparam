// main.bicepparam

// Link this parameter file to the main Bicep template
using '../main.bicep'

// Define the parameter values
param companyPrefix = 'sdt'
param purpose = 'aidetector'
param environment = 'prod'
param location = 'uksouth' // Azure region full name

// Environment-specific parameters for Production
parameters: {
  // companyPrefix: 'sdt' // Default in main.bicep
  // purpose: 'aidetector' // Default in main.bicep
  // location: 'uksouth' // Default in main.bicep

  // --- Container App --- 
  // REQUIRED: Specify the production container image
  containerImage: '<your-acr-name>.azurecr.io/<your-image-name>:<your-prod-tag>'
  // Defaults from main.bicep for prod are likely sufficient, but can be overridden:
  // containerAppCpuCoreCount: 1.0 
  // containerAppMemoryGiB: '2.0Gi'
  // containerAppMinReplicas: 1
  // containerAppMaxReplicas: 5

  // --- Secrets --- 
  // REQUIRED: Provide actual production secret values here or via command-line/CI/CD
  cosmosDbConnectionString: '<COSMOS_DB_CONNECTION_STRING_PROD>'
  kindeClientSecret: '<KINDE_CLIENT_SECRET_PROD>'
  stripeSecretKey: '<STRIPE_SECRET_KEY_PROD>'
  storageConnectionString: '<AZURE_STORAGE_CONNECTION_STRING_PROD>'
}
