param(
    [string]$Version = 'v0.1.0'
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root "release\$Version"

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Push-Location "$Root\backend"
try {
    $requirements = & uv export --locked --no-dev --no-emit-project --format requirements-txt
    if ($LASTEXITCODE -ne 0) { throw 'uv export failed.' }
    $requirements | Out-File -LiteralPath "$ReleaseDir\requirements.txt" -Encoding utf8

    $previousWarnings = $env:PYTHONWARNINGS
    $env:PYTHONWARNINGS = 'ignore:The Component this BOM is describing'
    & uv run cyclonedx-py requirements `
        "$ReleaseDir\requirements.txt" `
        --pyproject "$Root\backend\pyproject.toml" `
        --output-reproducible `
        --of JSON `
        -o "$ReleaseDir\sbom-python.cdx.json"
    $env:PYTHONWARNINGS = $previousWarnings
    if ($LASTEXITCODE -ne 0) { throw 'Python SBOM generation failed.' }

    $directDependencyJson = & uv run python -c "import json,tomllib; p=tomllib.load(open('pyproject.toml','rb')); print(json.dumps([d.split('[',1)[0].split('=',1)[0].split('<',1)[0].split('>',1)[0].strip() for d in p['project']['dependencies']]))"
    if ($LASTEXITCODE -ne 0) { throw 'Reading direct Python dependencies failed.' }
}
finally {
    Pop-Location
}

$pythonBomPath = "$ReleaseDir\sbom-python.cdx.json"
$pythonBom = Get-Content -Raw -LiteralPath $pythonBomPath | ConvertFrom-Json
$directDependencyNames = $directDependencyJson | ConvertFrom-Json
$componentRefsByName = @{}
foreach ($component in $pythonBom.components) {
    $componentRefsByName[[string]$component.name] = [string]$component.'bom-ref'
}
$directRefs = foreach ($dependencyName in $directDependencyNames) {
    $componentRef = $componentRefsByName[[string]$dependencyName]
    if ([string]::IsNullOrWhiteSpace($componentRef)) {
        throw "Python SBOM is missing direct dependency $dependencyName."
    }
    $componentRef
}
$rootRef = [string]$pythonBom.metadata.component.'bom-ref'
$rootDependency = $pythonBom.dependencies | Where-Object { $_.ref -eq $rootRef }
if ($null -eq $rootDependency) { throw 'Python SBOM is missing its root dependency node.' }
$rootDependency | Add-Member -NotePropertyName dependsOn -NotePropertyValue @($directRefs | Sort-Object) -Force
$pythonBom | ConvertTo-Json -Depth 100 | Out-File -LiteralPath $pythonBomPath -Encoding utf8

Push-Location "$Root\backend"
try {
    & uv run python -c "import json,sys; from cyclonedx.schema import SchemaVersion; from cyclonedx.validation.json import JsonStrictValidator; data=json.load(open(sys.argv[1],encoding='utf-8-sig')); error=JsonStrictValidator(SchemaVersion.V1_6).validate_str(json.dumps(data)); print(error or 'Python CycloneDX SBOM: valid'); raise SystemExit(bool(error))" "$pythonBomPath"
    if ($LASTEXITCODE -ne 0) { throw 'Python SBOM strict validation failed.' }
}
finally {
    Pop-Location
}

Push-Location $Root
try {
    $licenseJson = & pnpm.cmd licenses list --prod --json
    if ($LASTEXITCODE -ne 0) { throw 'pnpm license inventory failed.' }
}
finally {
    Pop-Location
}

$licenseGroups = $licenseJson | ConvertFrom-Json
$components = @{}
foreach ($licenseGroup in $licenseGroups.PSObject.Properties) {
    $licenseExpression = $licenseGroup.Name
    foreach ($dependency in $licenseGroup.Value) {
        foreach ($versionValue in $dependency.versions) {
            $name = [string]$dependency.name
            $version = [string]$versionValue
            $key = "$name@$version"

            if ($name.StartsWith('@')) {
                $nameParts = $name.Substring(1).Split('/', 2)
                $purlName = "%40$([uri]::EscapeDataString($nameParts[0]))/$([uri]::EscapeDataString($nameParts[1]))"
            }
            else {
                $purlName = [uri]::EscapeDataString($name)
            }

            $components[$key] = [ordered]@{
                type = 'library'
                name = $name
                version = $version
                license = $licenseExpression
                purl = "pkg:npm/$purlName@$version"
            }
        }
    }
}

$dependencyInventory = @($components.Values | Sort-Object name, version)
$dependencyInventory | ConvertTo-Json -Depth 5 | Out-File -LiteralPath "$ReleaseDir\pnpm-dependencies.json" -Encoding utf8

$licenseInventory = foreach ($component in $dependencyInventory) {
    [ordered]@{
        name = $component.name
        version = $component.version
        license = $component.license
    }
}
@($licenseInventory) | ConvertTo-Json -Depth 5 | Out-File -LiteralPath "$ReleaseDir\licenses-npm.json" -Encoding utf8

$webVersion = $Version.TrimStart('v')
$webRootRef = "pkg:npm/%40greenflex/web@$webVersion"
$sbom = [ordered]@{
    bomFormat = 'CycloneDX'
    specVersion = '1.6'
    version = 1
    metadata = [ordered]@{
        component = [ordered]@{
            'bom-ref' = $webRootRef
            type = 'application'
            name = '@greenflex/web'
            version = $webVersion
            purl = $webRootRef
        }
    }
    components = @($dependencyInventory | ForEach-Object {
        [ordered]@{
            'bom-ref' = $_.purl
            type = $_.type
            name = $_.name
            version = $_.version
            licenses = @([ordered]@{ expression = $_.license })
            purl = $_.purl
        }
    })
    dependencies = @(
        [ordered]@{
            ref = $webRootRef
            dependsOn = @($dependencyInventory.purl | Sort-Object)
        }
        $dependencyInventory | ForEach-Object { [ordered]@{ ref = $_.purl } }
    )
}
$sbom | ConvertTo-Json -Depth 8 | Out-File -LiteralPath "$ReleaseDir\sbom-web.cdx.json" -Encoding utf8

foreach ($jsonName in @('licenses-npm.json', 'pnpm-dependencies.json', 'sbom-python.cdx.json', 'sbom-web.cdx.json')) {
    Get-Content -Raw -LiteralPath "$ReleaseDir\$jsonName" | ConvertFrom-Json | Out-Null
}

Push-Location "$Root\backend"
try {
    & uv run python -c "import json,sys; from cyclonedx.schema import SchemaVersion; from cyclonedx.validation.json import JsonStrictValidator; data=json.load(open(sys.argv[1],encoding='utf-8-sig')); error=JsonStrictValidator(SchemaVersion.V1_6).validate_str(json.dumps(data)); print(error or 'Web CycloneDX SBOM: valid'); raise SystemExit(bool(error))" "$ReleaseDir\sbom-web.cdx.json"
    if ($LASTEXITCODE -ne 0) { throw 'Web SBOM strict validation failed.' }
}
finally {
    Pop-Location
}

$privateMarkers = @($Root, $env:USERPROFILE) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
foreach ($artifact in Get-ChildItem -LiteralPath $ReleaseDir -File) {
    $content = Get-Content -Raw -LiteralPath $artifact.FullName
    foreach ($marker in $privateMarkers) {
        if ($content.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "Release artifact $($artifact.Name) contains a private local path."
        }
    }
}

$checksums = Get-ChildItem -LiteralPath $ReleaseDir -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
}
$checksums | Out-File -LiteralPath "$ReleaseDir\SHA256SUMS.txt" -Encoding ascii

$expectedArtifacts = @(Get-ChildItem -LiteralPath $ReleaseDir -File | Where-Object Name -ne 'SHA256SUMS.txt').Count
$checksumLines = @(Get-Content -LiteralPath "$ReleaseDir\SHA256SUMS.txt").Count
if ($checksumLines -ne $expectedArtifacts) {
    throw "Checksum manifest has $checksumLines entries; expected $expectedArtifacts."
}

Write-Host "Release artifacts generated in $ReleaseDir" -ForegroundColor Green
