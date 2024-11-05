import strawberry
from strawberry.file_uploads import Upload
from typing import Optional
from datetime import datetime
import boto3
import os
from sqlmodel import select, update

from models import PDF
from database import get_session


BUCKET_NAME = os.getenv('BUCKET_NAME')

@strawberry.type
class PDFType:
    id: int
    filename: str
    s3_url: str
    summary: Optional[str]
    upload_date: datetime

def convert_to_strawberry_type(pdf: PDF) -> PDFType:
    return PDFType(
        id=pdf.id,
        filename=pdf.filename,
        s3_url=pdf.s3_url,
        summary=pdf.summary,
        upload_date=pdf.upload_date
    )

@strawberry.type
class Query:
    @strawberry.field
    async def pdfs(self) -> list[PDFType]:
        async with get_session() as session:
            statement = select(PDF).order_by(PDF.upload_date.desc())
            result = await session.execute(statement)
            pdfs = result.scalars().all()
            return [convert_to_strawberry_type(pdf) for pdf in pdfs]

    @strawberry.field
    async def pdf(self, pdf_id: int) -> Optional[PDFType]:
        async with get_session() as session:
            statement = select(PDF).where(PDF.id == pdf_id)
            result = await session.execute(statement)
            pdf = result.scalar_one_or_none()
            return convert_to_strawberry_type(pdf) if pdf else None

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def upload_pdf(self, file: Upload) -> PDFType:
        s3 = boto3.client("s3")

        # Upload to S3
        filename = file.filename
        s3.upload_fileobj(file.file, BUCKET_NAME, filename)
        s3_url = f"s3://{BUCKET_NAME}/{filename}"

        async with get_session() as session:
            # Create PDF record
            pdf = PDF(filename=filename, s3_url=s3_url)
            session.add(pdf)
            await session.commit()
            await session.refresh(pdf)

        return convert_to_strawberry_type(pdf)

    @strawberry.mutation
    async def update_pdf_summary(self, pdf_id: int, summary: str) -> Optional[PDFType]:
        async with get_session() as session:
            # Find the PDF
            statement = select(PDF).where(PDF.id == pdf_id)
            result = await session.execute(statement)
            pdf = result.scalar_one_or_none()

            if not pdf:
                return None

            # Update the summary
            pdf.summary = summary
            await session.commit()
            await session.refresh(pdf)

            return convert_to_strawberry_type(pdf)

    @strawberry.mutation
    async def delete_pdf(self, pdf_id: int) -> bool:
        async with get_session() as session:
            statement = select(PDF).where(PDF.id == pdf_id)
            result = await session.execute(statement)
            pdf = result.scalar_one_or_none()

            if pdf:
                # Delete from S3
                s3 = boto3.client("s3")
                s3.delete_object(Bucket=BUCKET_NAME, Key=pdf.filename)

                # Delete from database
                await session.delete(pdf)
                await session.commit()
                return True
            return False

schema = strawberry.federation.Schema(query=Query, mutation=Mutation)
