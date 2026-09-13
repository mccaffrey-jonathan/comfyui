# SPDX-License-Identifier: Apache-2.0
"""Generate a two-tier TEST certificate chain (root CA -> claim-signing leaf) for C2PA.

The C2PA SDK rejects single self-signed leaf certificates, so we mint a tiny
private root and issue the signing certificate from it.  Signed manifests
validate as *Valid* (cryptographically sound) but not *Trusted*: only
certificates chaining to the C2PA trust list are shown as trusted by public
verifiers.  Use these certificates for development only.
"""
from __future__ import annotations

import datetime as dt
import os


def generate_test_chain(organization: str = "ComfyUI Test", common_name: str = "ComfyUI Test C2PA Signer",
                        out_dir: str = ".", key_type: str = "ec256", days: int = 825,
                        overwrite: bool = False) -> dict:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    os.makedirs(out_dir, exist_ok=True)
    cert_path = os.path.join(out_dir, "c2pa_cert_chain.pem")
    key_path = os.path.join(out_dir, "c2pa_private_key.pem")
    root_path = os.path.join(out_dir, "c2pa_test_root.pem")
    if not overwrite and os.path.exists(cert_path) and os.path.exists(key_path):
        return {"cert_chain": cert_path, "private_key": key_path, "root": root_path, "created": False}

    def _key():
        if key_type == "ec256":
            return ec.generate_private_key(ec.SECP256R1())
        if key_type == "ec384":
            return ec.generate_private_key(ec.SECP384R1())
        if key_type == "rsa":
            return rsa.generate_private_key(public_exponent=65537, key_size=3072)
        if key_type == "ed25519":
            return ed25519.Ed25519PrivateKey.generate()
        raise ValueError(key_type)

    def _sign(builder, key):
        if isinstance(key, ed25519.Ed25519PrivateKey):
            return builder.sign(key, None)
        return builder.sign(key, hashes.SHA256())

    now = dt.datetime.now(dt.timezone.utc)
    root_key = _key()
    root_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "FOR TESTING ONLY"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{organization} Test Root CA"),
    ])
    root_cert = _sign(
        x509.CertificateBuilder()
        .subject_name(root_name).issuer_name(root_name).public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False),
        root_key,
    )

    leaf_key = _key()
    leaf_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "FOR TESTING ONLY"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    leaf_cert = _sign(
        x509.CertificateBuilder()
        .subject_name(leaf_name).issuer_name(root_name).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_cert_sign=False,
                                     crl_sign=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False),
        root_key,
    )

    chain_pem = leaf_cert.public_bytes(serialization.Encoding.PEM) + root_cert.public_bytes(serialization.Encoding.PEM)
    key_pem = leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
    with open(cert_path, "wb") as fh:
        fh.write(chain_pem)
    with open(key_path, "wb") as fh:
        fh.write(key_pem)
    try:
        os.chmod(key_path, 0o600)
    except OSError:  # pragma: no cover
        pass
    with open(root_path, "wb") as fh:
        fh.write(root_cert.public_bytes(serialization.Encoding.PEM))
    alg = {"ec256": "es256", "ec384": "es384", "rsa": "ps256", "ed25519": "ed25519"}[key_type]
    return {"cert_chain": cert_path, "private_key": key_path, "root": root_path, "alg": alg, "created": True}
