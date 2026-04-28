package syndication

// autoscout24_ch.go — AutoScout24 Switzerland variant.
// The adapter is created in autoscout24.go init() via NewAutoScout24("CH").
// Switzerland uses CHF as currency; callers must set PlatformListing.Currency = "CHF".

// AutoScout24CHName is the canonical platform name for AutoScout24 Switzerland.
const AutoScout24CHName = "autoscout24_ch"
