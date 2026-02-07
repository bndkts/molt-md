from django.db import models
import uuid


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_encrypted = models.BinaryField()  # Encrypted with read key
    nonce = models.BinaryField()
    read_key_hash = models.BinaryField(null=True)  # SHA-256 hash of read key for verification
    version = models.IntegerField(default=1)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        indexes = [
            models.Index(fields=["last_accessed"]),
        ]

    def __str__(self):
        return f"Document {self.id} (v{self.version})"


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_encrypted = models.BinaryField()  # Encrypted JSON blob with read key
    nonce = models.BinaryField()
    read_key_hash = models.BinaryField(null=True)  # SHA-256 hash of read key for verification
    version = models.IntegerField(default=1)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workspaces"
        indexes = [
            models.Index(fields=["last_accessed"]),
        ]

    def __str__(self):
        return f"Workspace {self.id} (v{self.version})"
