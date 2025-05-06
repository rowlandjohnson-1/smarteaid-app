// -------- infra/main.bicep --------
// MODIFIED:
// - Removed explicit 'dependsOn: [rg]' for the 'resources' module,
//   as this dependency is inferred by 'scope: rg'.

@description('Company prefix for resource names.')
param companyPrefix string = 'sdt'

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string = 'aidetector'

@description('The environment (e.g., dev, test, prod).')
param environment string = 'dev'

@description('Primary Azure region for resource deployment.')
param location string = 'uksouth'

// --- Container App Parameters needed by resources module ---
@description('Required. Specifies the container image to deploy (e.g., myacr.azurecr.io/myapp:latest).')
param containerImage string

@description('Optional. Specifies the CPU allocation for the container app.')
param containerAppCpuCoreCount string = (environment == 'prod') ? '1.0' : '0.5'

@description('Optional. Specifies the memory allocation for the container app.')
param containerAppMemoryGiB string = (environment == 'prod') ? '2.0Gi' : '1.0Gi'

@description('Optional. Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 1 // Changed dev default from 0 to 1 to match resources.bicep

@description('Optional. Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2


// --- Secure Parameters needed by resources module ---
@secure()
@description('Required. MongoDB connection string (formerly Cosmos DB).')
param mongoDbUrl string

@secure()
@description('Required. Kinde client secret for backend validation.')
param kindeClientSecret string

@secure()
@description('Required. Stripe secret key (use test key for dev/stg, live key for prod).')
param stripeSecretKey string

@secure()
@description('Required. Connection string for Azure Blob Storage.')
param storageConnectionString string

// --- Kinde non-secret parameters ---
@description('Required. Kinde domain for authentication.')
param kindeDomain string

@description('Required. Kinde audience for authentication.')
param kindeAudience string
// --- End Kinde non-secret parameters ---

// Define the target scope for the Bicep file
targetScope = 'subscription'

// --- Variables ---
var locationShort = 'uks' // Assuming 'uks' for 'uksouth'. Adjust if needed for other regions.
var rgName = 'rg-${companyPrefix}-${locationShort}-${purpose}-${environment}'

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector' // Consistent application tag
    purpose: purpose
  }
}

// Deploy all resources within the resource group using a module
module resources './resources.bicep' = { // Using relative path for the module
  name: 'resourcesDeployment-${environment}' // Deployment name for the module
  scope: rg // Deploys the module's resources into the 'rg' resource group
  params: {
    // Pass down standard parameters
    companyPrefix: companyPrefix
    purpose: purpose
    environment: environment
    location: location
    locationShort: locationShort

    // Pass down Container App parameters
    containerImage: containerImage
    containerAppCpuCoreCount: containerAppCpuCoreCount
    containerAppMemoryGiB: containerAppMemoryGiB
    containerAppMinReplicas: containerAppMinReplicas
    containerAppMaxReplicas: containerAppMaxReplicas

    // Pass down Secure parameters
    mongoDbUrl: mongoDbUrl
    kindeClientSecret: kindeClientSecret
    stripeSecretKey: stripeSecretKey
    storageConnectionString: storageConnectionString

    // Pass down Kinde non-secret parameters
    kindeDomain: kindeDomain
    kindeAudience: kindeAudience
  }
  // Explicit 'dependsOn: [rg]' removed as it's inferred by 'scope: rg'
}

// --- Outputs ---
output resourceGroupName string = rg.name
output keyVaultName string = resources.outputs.keyVaultName
output storageAccountName string = resources.outputs.storageAccountName
output cosmosDbAccountName string = resources.outputs.cosmosDbAccountName // Retained if still needed, though MongoDB is primary
output containerAppsEnvId string = resources.outputs.containerAppsEnvId
output containerAppName string = resources.outputs.containerAppName
output containerAppPrincipalId string = resources.outputs.containerAppPrincipalId
output acrLoginServer string = resources.outputs.acrLoginServer
output acrName string = resources.outputs.acrName
