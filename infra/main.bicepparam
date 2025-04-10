// main.bicepparam

// Link this parameter file to the main Bicep template
using 'main.bicep'

// Define the parameter values
param companyPrefix = 'sdt'
param purpose = 'aidetector'
param environment = 'dev'
param location = 'uksouth' // Azure region full name
