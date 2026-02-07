from django.db import models
import uuid


class Document(models.Model):
    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # type: ignore[assignment]
    content_encrypted: models.BinaryField = models.BinaryField()  # type: ignore[assignment]
    nonce: models.BinaryField = models.BinaryField()  # type: ignore[assignment]
    version: models.IntegerField = models.IntegerField(default=1)  # type: ignore[assignment]
    last_accessed: models.DateTimeField = models.DateTimeField(auto_now=True)  # type: ignore[assignment]
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)  # type: ignore[assignment]

    class Meta:
        db_table = "documents"
        indexes = [
            models.Index(fields=["last_accessed"]),
        ]

    def __str__(self):
        return f"Document {self.id} (v{self.version})"
