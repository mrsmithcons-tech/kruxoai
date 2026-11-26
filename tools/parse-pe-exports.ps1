param([string]$File, [string]$TargetRvaHex)
# Find the exported function nearest at-or-below a target RVA in a PE file.
# Usage: powershell -File parse-pe-exports.ps1 <dll-path> 0x12561
$target = [Convert]::ToUInt32($TargetRvaHex, 16)
$bytes = [System.IO.File]::ReadAllBytes($File)
function u16([int]$o) { return [System.BitConverter]::ToUInt16($bytes, $o) }
function u32([int]$o) { return [System.BitConverter]::ToUInt32($bytes, $o) }
if ([System.Text.Encoding]::ASCII.GetString($bytes, 0, 2) -ne 'MZ') { Write-Output 'NOT A PE FILE'; exit 1 }
$peOff = u32 0x3C
$numSections = u16 ($peOff + 6)
$optOff = $peOff + 24
$magic = u16 $optOff
$is64 = ($magic -eq 0x20B)
$ddOff = $optOff + 96
if ($is64) { $ddOff = $optOff + 112 }
$expRva = u32 $ddOff; $expSize = u32 ($ddOff + 4)
$secOff = $ddOff + 128
function RvaToOff([uint32]$rva) {
    for ($i = 0; $i -lt $numSections; $i++) {
        $s = $secOff + $i * 40
        $vsize = u32 ($s + 8); $vaddr = u32 ($s + 12); $rawSize = u32 ($s + 16); $rawPtr = u32 ($s + 20)
        if ($rva -ge $vaddr -and $rva -lt ($vaddr + [math]::Max($vsize, $rawSize))) { return ($rawPtr + ($rva - $vaddr)) }
    }
    return [int]$rva
}
function ReadStr([int]$off) {
    $end = $off; while ($bytes[$end] -ne 0) { $end++ }
    return [System.Text.Encoding]::ASCII.GetString($bytes, $off, $end - $off)
}
$expOff = RvaToOff $expRva
$numFuncs = u32 ($expOff + 20); $numNames = u32 ($expOff + 24)
$addrFuncs = u32 ($expOff + 28); $addrNames = u32 ($expOff + 32); $addrOrds = u32 ($expOff + 36)
Write-Output ("file: {0}  exports: {1} named, {2} total" -f (Split-Path $File -Leaf), $numNames, $numFuncs)
# Pass 1: nearest function RVA at/below target (integers only — fast).
$bestBelowRva = 0; $bestBelowOrd = -1; $bestAboveRva = [uint32]::MaxValue; $bestAboveOrd = -1
$funcsOff = RvaToOff $addrFuncs
for ($ord = 0; $ord -lt $numFuncs; $ord++) {
    $frva = u32 ($funcsOff + $ord * 4)
    if ($frva -le $target -and $frva -gt $bestBelowRva) { $bestBelowRva = $frva; $bestBelowOrd = $ord }
    if ($frva -gt $target -and $frva -lt $bestAboveRva) { $bestAboveRva = $frva; $bestAboveOrd = $ord }
}
# Pass 2: name for one ordinal (scan ordinals only; read the string on match).
function Get-NameForOrd([int]$want) {
    $namesOff = RvaToOff $addrNames; $ordsOff = RvaToOff $addrOrds
    for ($i = 0; $i -lt $numNames; $i++) {
        if ((u16 ($ordsOff + $i * 2)) -eq $want) {
            $nameRva = u32 ($namesOff + $i * 4)
            return (ReadStr (RvaToOff $nameRva))
        }
    }
    return '(unnamed)'
}
Write-Output ("target RVA: 0x{0:X}" -f $target)
if ($bestBelowOrd -ge 0) { Write-Output ("nearest export at/below: {0} @ 0x{1:X}  (target is +0x{2:X} inside it)" -f (Get-NameForOrd $bestBelowOrd), $bestBelowRva, ($target - $bestBelowRva)) }
if ($bestAboveOrd -ge 0) { Write-Output ("next export above:      {0} @ 0x{1:X}" -f (Get-NameForOrd $bestAboveOrd), $bestAboveRva) }
