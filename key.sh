cat > /tmp/download_ksef_keys.sh << 'EOF'
#!/bin/bash

KEYDIR="/home/fakturownia/app/ksef-pubkey"

echo "Próba 1: Pobieranie z GitHub (PEM)"
curl -L -f https://raw.githubusercontent.com/CIRFMF/ksef-docs/main/auth/ksef-test-encryption-public-key.pem \
  -o "$KEYDIR/publicKey.pem" 2>/dev/null

if [ -f "$KEYDIR/publicKey.pem" ]; then
    echo "✓ Pobrано z GitHub (PEM)"
    head -3 "$KEYDIR/publicKey.pem"
    exit 0
fi

echo "Próba 2: Pobieranie z API KSeF (DER)"
curl -L -f https://ksef-test.mf.gov.pl/api/v2/common/Encryption/PublicKey \
  -H "Accept: application/octet-stream" \
  -o "$KEYDIR/publicKey.der" 2>/dev/null

if [ -f "$KEYDIR/publicKey.der" ]; then
    echo "✓ Pobrано z API (DER)"
    ls -lh "$KEYDIR/publicKey.der"
    exit 0
fi

echo "Próba 3: Pobieranie przez wget (PEM)"
wget -q https://raw.githubusercontent.com/CIRFMF/ksef-docs/main/auth/ksef-test-encryption-public-key.pem \
  -O "$KEYDIR/publicKey.pem" 2>/dev/null

if [ -f "$KEYDIR/publicKey.pem" ]; then
    echo "✓ Pobrано przez wget (PEM)"
    head -3 "$KEYDIR/publicKey.pem"
    exit 0
fi

echo "❌ Wszystkie próby nie powiodły się"
exit 1
EOF

chmod +x /tmp/download_ksef_keys.sh
bash /tmp/download_ksef_keys.sh
