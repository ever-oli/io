"""Cosign integration for release signing.

Signs release artifacts using Sigstore/cosign for supply chain security.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SigningResult:
    """Result of a signing operation."""

    success: bool
    artifact: Path
    signature: Optional[Path] = None
    certificate: Optional[Path] = None
    error: Optional[str] = None


class CosignSigner:
    """Signs artifacts using cosign."""

    def __init__(self, cosign_bin: str = "cosign"):
        self.cosign_bin = cosign_bin
        self._checked = False
        self._available = False

    def check_available(self) -> bool:
        """Check if cosign is installed."""
        if self._checked:
            return self._available

        try:
            result = subprocess.run(
                [self.cosign_bin, "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._available = False

        self._checked = True
        return self._available

    def sign_artifact(
        self,
        artifact: Path,
        output_dir: Optional[Path] = None,
        identity: Optional[str] = None,
        issuer: Optional[str] = None,
    ) -> SigningResult:
        """Sign an artifact using cosign.

        Uses keyless signing via Sigstore by default.
        """
        if not self.check_available():
            return SigningResult(
                success=False,
                artifact=artifact,
                error="cosign not installed. Install: https://docs.sigstore.dev/cosign/installation/",
            )

        if not artifact.exists():
            return SigningResult(
                success=False,
                artifact=artifact,
                error=f"Artifact not found: {artifact}",
            )

        if output_dir is None:
            output_dir = artifact.parent

        output_dir.mkdir(parents=True, exist_ok=True)

        sig_path = output_dir / f"{artifact.name}.sig"
        cert_path = output_dir / f"{artifact.name}.cert"

        cmd = [
            self.cosign_bin,
            "sign-blob",
            str(artifact),
            "--output-signature",
            str(sig_path),
            "--output-certificate",
            str(cert_path),
        ]

        # Add identity flags if provided
        if identity:
            cmd.extend(["--identity", identity])
        if issuer:
            cmd.extend(["--issuer", issuer])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info(f"Signed: {artifact}")
                return SigningResult(
                    success=True,
                    artifact=artifact,
                    signature=sig_path,
                    certificate=cert_path,
                )
            else:
                return SigningResult(
                    success=False,
                    artifact=artifact,
                    error=result.stderr or "Unknown error",
                )

        except subprocess.TimeoutExpired:
            return SigningResult(
                success=False,
                artifact=artifact,
                error="Signing timed out",
            )
        except Exception as e:
            return SigningResult(
                success=False,
                artifact=artifact,
                error=str(e),
            )

    def verify_artifact(
        self,
        artifact: Path,
        signature: Path,
        certificate: Optional[Path] = None,
    ) -> SigningResult:
        """Verify a signed artifact."""
        if not self.check_available():
            return SigningResult(
                success=False,
                artifact=artifact,
                error="cosign not installed",
            )

        cmd = [
            self.cosign_bin,
            "verify-blob",
            str(artifact),
            "--signature",
            str(signature),
        ]

        if certificate:
            cmd.extend(["--certificate", str(certificate)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return SigningResult(
                    success=True,
                    artifact=artifact,
                    signature=signature,
                    certificate=certificate,
                )
            else:
                return SigningResult(
                    success=False,
                    artifact=artifact,
                    error=result.stderr or "Verification failed",
                )

        except Exception as e:
            return SigningResult(
                success=False,
                artifact=artifact,
                error=str(e),
            )

    def sign_release(
        self,
        artifacts: List[Path],
        output_dir: Path,
    ) -> List[SigningResult]:
        """Sign all artifacts in a release."""
        results = []

        for artifact in artifacts:
            result = self.sign_artifact(artifact, output_dir)
            results.append(result)

        return results


def install_cosign() -> bool:
    """Install cosign if not present.

    Downloads and installs cosign to ~/.io/bin/
    """
    io_bin = Path.home() / ".io" / "bin"
    io_bin.mkdir(parents=True, exist_ok=True)

    cosign_path = io_bin / "cosign"

    # Check if already installed
    if cosign_path.exists():
        return True

    # Installation would require platform-specific downloads
    # For now, just point to docs
    logger.info("Please install cosign manually:")
    logger.info("  https://docs.sigstore.dev/cosign/installation/")
    logger.info(f"Or install to: {cosign_path}")

    return False
