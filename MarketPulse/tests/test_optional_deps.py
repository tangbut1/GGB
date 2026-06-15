"""Tests for optional dependency guards."""

import pytest
from unittest.mock import patch

def test_optional_pdf_dependency_missing_message():
    """Verify that using PDF export without reportlab raises a clear ImportError."""
    from src.report.export_pdf import PDFReportGenerator
    
    # Simulate reportlab not being installed by patching _HAS_REPORTLAB to False
    with patch("src.report.export_pdf._HAS_REPORTLAB", False):
        with pytest.raises(ImportError) as exc_info:
            generator = PDFReportGenerator()
        
        assert "pip install reportlab" in str(exc_info.value)

def test_optional_docx_dependency_missing_message():
    """Verify that using DOCX export without python-docx raises a clear ImportError."""
    from src.report.export_doc import DOCXReportGenerator
    
    # Simulate python-docx not being installed by patching _HAS_DOCX to False
    with patch("src.report.export_doc._HAS_DOCX", False):
        generator = DOCXReportGenerator()
        with pytest.raises(ImportError) as exc_info:
            generator.create_report({}, {}, [], {}, "", "dummy.docx")
        
        assert "pip install python-docx" in str(exc_info.value)
