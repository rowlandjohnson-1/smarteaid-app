
// Deploy user MI
az deployment sub create --name "userMIDeployDev" --location "uksouth" --template-file ".\infra\managedIdentities\mi.bicep" --parameters '.\infra\managedIdentities\params\miDev.bicepparam'
az deployment sub create --name "userMIDeployStaging" --location "uksouth" --template-file ".\bicep\managedIdentities\mi.bicep" --parameters '.\bicep\managedIdentities\params\miStaging.bicepparam'
az deployment sub create --name "userMIDeployProd" --location "uksouth" --template-file ".\bicep\managedIdentities\mi.bicep" --parameters '.\bicep\managedIdentities\params\miProd.bicepparam'

//Deploy Key Vault
az deployment sub create --name "keyVaultDeployDev" --location "uksouth" --template-file ".\infra\keyVault\kv.bicep" --parameters '.\infra\keyVault\params\devKv.bicepparam'
az deployment sub create --name "keyVaultDeployStaging" --location "uksouth" --template-file ".\bicep\keyVault\kv.bicep" --parameters '.\bicep\keyVault\params\stagingKv.bicepparam'
az deployment sub create --name "keyVaultDeployProd" --location "uksouth" --template-file ".\bicep\keyVault\kv.bicep" --parameters '.\bicep\keyVault\params\prodKv.bicepparam'

//Deploy MongoDB
az deployment sub create --name "mongoDBDeployDev" --location "uksouth" --template-file ".\infra\cosmosDb\mongo.bicep" --parameters '.\infra\cosmosDb\params\mongoDev.bicepparam'
az deployment sub create --name "mongoDBDeployStaging" --location "uksouth" --template-file ".\bicep\cosmosDb\mongo.bicep" --parameters '.\bicep\cosmosDb\params\mongoStaging.bicepparam'
az deployment sub create --name "mongoDBDeployProd" --location "uksouth" --template-file ".\bicep\cosmosDb\mongo.bicep" --parameters '.\bicep\cosmosDb\params\mongoProd.bicepparam'

//Deploy ACR
az deployment sub create --name "acrDeployDev" --location "uksouth" --template-file ".\infra\containerRegistry\acr.bicep" --parameters '.\infra\containerRegistry\params\acrDev.bicepparam'
az deployment sub create --name "acrDeployStaging" --location "uksouth" --template-file ".\bicep\containerRegistry\acr.bicep" --parameters '.\bicep\containerRegistry\params\acrStaging.bicepparam'
az deployment sub create --name "acrDeployProd" --location "uksouth" --template-file ".\bicep\containerRegistry\acr.bicep" --parameters '.\bicep\containerRegistry\params\acrProd.bicepparam'