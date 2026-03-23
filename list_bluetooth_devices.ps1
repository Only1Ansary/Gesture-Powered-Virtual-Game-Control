# List Bluetooth devices Windows knows about (paired / enumerated).
# Look for "BTHENUM\DEV_XXXXXXXXXXXX" — the 12 hex digits are the MAC (add colons).
# Example: DEV_7C03AB2A0CCE  ->  7c:03:ab:2a:0c:ce  for admin_bluetooth_mac in config.json

Write-Host "`nBluetooth devices (check FriendlyName + InstanceId):`n" -ForegroundColor Cyan
Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -match 'BTHENUM\\DEV_[0-9A-F]{12}' } |
    ForEach-Object {
        if ($_.InstanceId -match 'DEV_([0-9A-F]{12})') {
            $raw = $Matches[1]
            $mac = ($raw -split '(..)' | Where-Object { $_ }) -join ':'
            [PSCustomObject]@{
                FriendlyName = $_.FriendlyName
                MAC          = $mac.ToLower()
                Status       = $_.Status
            }
        }
    } | Format-Table -AutoSize

Write-Host "Copy the MAC of YOUR phone into config.json -> admin_bluetooth_mac`n" -ForegroundColor Yellow
