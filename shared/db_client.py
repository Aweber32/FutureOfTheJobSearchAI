import pyodbc
import os
import json
import logging
import numpy as np
import struct
from typing import Optional, Dict, Any
from contextlib import contextmanager
from azure.identity import DefaultAzureCredential

class DBClient:
    """Database client with support for Managed Identity (production) and connection string (local)."""
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize DB client with automatic detection of authentication method.
        
        Args:
            connection_string: Optional connection string. If None, reads from environment.
        
        Environment Variables:
            SQL_CONNECTION_STRING: Full connection string (for local dev)
            AZURE_SQL_SERVER: Server name (for Managed Identity)
            AZURE_SQL_DATABASE: Database name (for Managed Identity)
            USE_MANAGED_IDENTITY: Set to "true" to force Managed Identity
        """
        self.conn_str = self._build_connection_string(connection_string)
        logging.info("DBClient initialized with appropriate authentication method")
    
    def _build_connection_string(self, connection_string: Optional[str] = None) -> str:
        """
        Build connection string based on environment (local vs production).
        
        Production: Uses Managed Identity
        Local: Uses Active Directory Default (falls back to local credentials)
        """
        # If connection string provided explicitly, use it
        if connection_string:
            return connection_string
        
        # Check if explicit connection string provided in environment
        env_conn_str = os.getenv("SQL_CONNECTION_STRING")
        if env_conn_str:
            logging.info("Using connection string from SQL_CONNECTION_STRING")
            return env_conn_str
        
        # Check for Managed Identity mode
        use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"
        
        # Get server and database from environment
        server = os.getenv("AZURE_SQL_SERVER", "futureofthejobsearch.database.windows.net")
        database = os.getenv("AZURE_SQL_DATABASE", "qa-futureofthejobsearch")
        
        if use_managed_identity or os.getenv("AZURE_FUNCTIONS_ENVIRONMENT") == "Production":
            # Production: Use Managed Identity
            conn_str = (
                f"Server=tcp:{server},1433;"
                f"Database={database};"
                f"Authentication=Active Directory Managed Identity;"
                f"Encrypt=True;"
                f"TrustServerCertificate=False;"
                f"Connection Timeout=30;"
            )
            logging.info(f"Using Managed Identity for Azure SQL: {database}")
        else:
            # Local: Use Active Directory Default (supports local credentials)
            conn_str = (
                f"Server=tcp:{server},1433;"
                f"Initial Catalog={database};"
                f"Encrypt=True;"
                f"TrustServerCertificate=False;"
                f"Connection Timeout=30;"
                f"Authentication=Active Directory Default;"
            )
            logging.info(f"Using Active Directory Default for Azure SQL: {database}")
        
        return conn_str
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with automatic cleanup and error handling."""
        conn = None
        try:
            # Try to get Azure AD token for SQL
            credential = DefaultAzureCredential()
            token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
            token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
            
            # Connect without authentication in connection string, use token instead
            conn_str_no_auth = self.conn_str.replace("Authentication=Active Directory Default;", "")
            conn_str_no_auth = conn_str_no_auth.replace("Authentication=ActiveDirectoryIntegrated;", "")
            conn_str_no_auth = conn_str_no_auth.replace("Authentication=ActiveDirectoryInteractive;", "")
            
            # Add Driver if missing - detect platform
            if "Driver=" not in conn_str_no_auth:
                import platform
                if platform.system() == "Linux":
                    # Linux uses ODBC Driver 18 or 17 for SQL Server
                    conn_str_no_auth = "Driver={ODBC Driver 18 for SQL Server};" + conn_str_no_auth
                else:
                    # Windows
                    conn_str_no_auth = "Driver={ODBC Driver 17 for SQL Server};" + conn_str_no_auth
            
            conn = pyodbc.connect(conn_str_no_auth, attrs_before={1256: token_struct}, timeout=30)
            logging.debug("Database connection established with Azure AD token")
            yield conn
            conn.commit()
        except pyodbc.Error as e:
            if conn:
                conn.rollback()
            logging.error(f"Database error: {str(e)}")
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"Unexpected error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
                logging.debug("Database connection closed")


    def save_embedding(self, entity_type: str, entity_id: str, embedding: np.ndarray, model_version: str) -> bool:
        """
        Save embedding vector to database using MERGE (upsert) operation.
        
        Args:
            entity_type: "Candidate" or "Position"
            entity_id: Unique identifier for the entity
            embedding: Numpy array containing the embedding vector
            model_version: Version identifier for the embedding model
            
        Returns:
            True if save was successful
            
        Raises:
            ValueError: If entity_type is invalid
            Exception: If database operation fails
        """
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower == "candidate":
            table = "dbo.SeekerEmbeddings"
            id_column = "SeekerId"
        elif entity_type_lower in ["position", "job"]:
            table = "dbo.PositionEmbeddings"
            id_column = "PositionId"
        else:
            raise ValueError(f"Invalid entity_type: {entity_type}. Must be 'Candidate' or 'Position'")
        
        # Convert embedding to bytes for SQL storage
        embedding_bytes = embedding.tobytes()
        
        # SQL MERGE statement for upsert operation
        sql = f"""
        MERGE {table} AS target
        USING (SELECT ? AS Id) AS source
        ON target.{id_column} = source.Id
        WHEN MATCHED THEN
            UPDATE SET Embedding = ?, ModelVersion = ?, UpdatedAt = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT ({id_column}, Embedding, ModelVersion, CreatedAt, UpdatedAt)
            VALUES (?, ?, ?, GETDATE(), GETDATE());
        """
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (entity_id, embedding_bytes, model_version, entity_id, embedding_bytes, model_version))
                logging.info(f"Successfully saved embedding for {entity_type} ID: {entity_id}")
                return True
        except Exception as e:
            logging.error(f"Failed to save embedding for {entity_type} ID {entity_id}: {str(e)}")
            raise

    def fetch_profile_text(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """
        Fetch text content and metadata for embedding generation.
        
        Args:
            entity_type: "Candidate" or "Position"
            entity_id: Unique identifier for the entity
            
        Returns:
            Dictionary containing:
                - text: Concatenated text for embedding
                - raw_data: Original data from database
                
        Raises:
            ValueError: If entity not found or entity_type is invalid
            Exception: If database operation fails
        """
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower == "candidate":
            table = "dbo.Seekers"
            id_column = "Id"
            sql = f"""
            SELECT 
                Id,
                FirstName,
                LastName,
                Skills,
                ProfessionalSummary,
                ExperienceJson,
                EducationJson,
                VisaStatus,
                PreferredSalary,
                WorkSetting,
                Travel,
                Relocate,
                Languages,
                Certifications,
                Interests,
                City,
                State
            FROM {table} 
            WHERE {id_column} = ?
            """
        elif entity_type_lower in ["position", "job"]:
            # First query: Get Position main data
            sql = f"""
            SELECT 
                p.Id,
                p.Title,
                p.Category,
                p.Description,
                p.EmploymentType,
                p.WorkSetting,
                p.TravelRequirements,
                p.SalaryType,
                p.SalaryValue,
                p.SalaryMin,
                p.SalaryMax,
                e.CompanyName
            FROM dbo.Positions p
            LEFT JOIN dbo.Employers e ON p.EmployerId = e.Id
            WHERE p.Id = ?
            """
        else:
            raise ValueError(f"Invalid entity_type: {entity_type}. Must be 'Candidate' or 'Position'")
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (entity_id,))
                row = cursor.fetchone()
                
                if not row:
                    raise ValueError(f"No {entity_type} found with ID = {entity_id}")
                
                # Parse row data based on entity type
                if entity_type_lower == "candidate":
                    # Unpack Seeker table fields
                    (seeker_id, first_name, last_name, skills, professional_summary,
                     experience_json, education_json, visa_status, preferred_salary,
                     work_setting, travel, relocate, languages, certifications, 
                     interests, city, state) = row
                    
                    # Parse JSON fields safely
                    experience = json.loads(experience_json) if experience_json else []
                    education = json.loads(education_json) if education_json else []
                    
                    # Build comprehensive text representation for embedding
                    text_parts = []
                    
                    # Name
                    if first_name or last_name:
                        name = f"{first_name or ''} {last_name or ''}".strip()
                        if name:
                            text_parts.append(f"Name: {name}")
                    
                    # Professional summary (most important for semantic matching)
                    if professional_summary:
                        text_parts.append(f"Professional Summary: {professional_summary}")
                    
                    # Skills (critical for matching)
                    if skills:
                        text_parts.append(f"Skills: {skills}")
                    
                    # Experience (structured JSON)
                    if experience:
                        exp_text = self._format_experience(experience)
                        if exp_text:
                            text_parts.append(f"Experience: {exp_text}")
                    
                    # Education (structured JSON)
                    if education:
                        edu_text = self._format_education(education)
                        if edu_text:
                            text_parts.append(f"Education: {edu_text}")
                    
                    # Location preferences
                    if city or state:
                        location = f"{city or ''}, {state or ''}".strip(', ')
                        text_parts.append(f"Location: {location}")
                    
                    # Work preferences
                    if work_setting:
                        text_parts.append(f"Work Setting: {work_setting}")
                    if travel:
                        text_parts.append(f"Travel: {travel}")
                    if relocate:
                        text_parts.append(f"Relocation: {relocate}")
                    
                    # Salary expectations
                    if preferred_salary:
                        text_parts.append(f"Preferred Salary: {preferred_salary}")
                    
                    # Additional qualifications
                    if certifications:
                        text_parts.append(f"Certifications: {certifications}")
                    if languages:
                        text_parts.append(f"Languages: {languages}")
                    
                    # Visa status (important for eligibility)
                    if visa_status:
                        text_parts.append(f"Visa Status: {visa_status}")
                    
                    # Interests (for culture fit)
                    if interests:
                        text_parts.append(f"Interests: {interests}")
                    
                    combined_text = " | ".join(text_parts)
                    
                    return {
                        "text": combined_text,
                        "raw_data": {
                            "id": seeker_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "skills": skills,
                            "professional_summary": professional_summary,
                            "experience": experience,
                            "education": education,
                            "visa_status": visa_status,
                            "preferred_salary": preferred_salary,
                            "work_setting": work_setting,
                            "travel": travel,
                            "relocate": relocate,
                            "languages": languages,
                            "certifications": certifications,
                            "interests": interests,
                            "city": city,
                            "state": state
                        }
                    }
                    
                else:  # Position
                    (position_id, title, category, description, employment_type, 
                     work_setting, travel_reqs, salary_type, salary_value,
                     salary_min, salary_max, company_name) = row
                    
                    # Fetch related collections - strings stored directly in junction tables
                    skills = []
                    education_reqs = []
                    experience_reqs = []
                    
                    try:
                        # Get Skills (stored as strings)
                        cursor.execute("""
                            SELECT Skill
                            FROM dbo.PositionSkill
                            WHERE PositionId = ?
                        """, (position_id,))
                        skills = [row[0] for row in cursor.fetchall() if row[0]]
                    except Exception as e:
                        logging.warning(f"Could not fetch skills for position {position_id}: {e}")
                    
                    try:
                        # Get Education requirements (stored as strings)
                        cursor.execute("""
                            SELECT Education
                            FROM dbo.PositionEducation
                            WHERE PositionId = ?
                        """, (position_id,))
                        education_reqs = [row[0] for row in cursor.fetchall() if row[0]]
                    except Exception as e:
                        logging.warning(f"Could not fetch education for position {position_id}: {e}")
                    
                    try:
                        # Get Experience requirements (stored as strings)
                        cursor.execute("""
                            SELECT Experience
                            FROM dbo.PositionExperience
                            WHERE PositionId = ?
                        """, (position_id,))
                        experience_reqs = [row[0] for row in cursor.fetchall() if row[0]]
                    except Exception as e:
                        logging.warning(f"Could not fetch experience for position {position_id}: {e}")
                    
                    # Build comprehensive text representation for position
                    text_parts = []
                    
                    # Job title and company
                    if title:
                        text_parts.append(f"Position: {title}")
                    if company_name:
                        text_parts.append(f"Company: {company_name}")
                    if category:
                        text_parts.append(f"Category: {category}")
                    
                    # Job description (most important for matching)
                    if description:
                        text_parts.append(f"Description: {description}")
                    
                    # Required skills (critical for matching)
                    if skills:
                        skills_str = ", ".join(skills)
                        text_parts.append(f"Required Skills: {skills_str}")
                    
                    # Education requirements
                    if education_reqs:
                        edu_str = ", ".join(education_reqs)
                        text_parts.append(f"Education Requirements: {edu_str}")
                    
                    # Experience requirements
                    if experience_reqs:
                        exp_str = ", ".join(experience_reqs)
                        text_parts.append(f"Experience Requirements: {exp_str}")
                    
                    # Job details
                    if employment_type:
                        text_parts.append(f"Employment Type: {employment_type}")
                    if work_setting:
                        text_parts.append(f"Work Setting: {work_setting}")
                    if travel_reqs:
                        text_parts.append(f"Travel: {travel_reqs}")
                    
                    # Compensation
                    salary_parts = []
                    if salary_type:
                        salary_parts.append(salary_type)
                    if salary_value:
                        salary_parts.append(f"${salary_value:,.0f}")
                    elif salary_min and salary_max:
                        salary_parts.append(f"${salary_min:,.0f} - ${salary_max:,.0f}")
                    elif salary_min:
                        salary_parts.append(f"From ${salary_min:,.0f}")
                    
                    if salary_parts:
                        text_parts.append(f"Salary: {' '.join(salary_parts)}")
                    
                    combined_text = " | ".join(text_parts)
                    
                    return {
                        "text": combined_text,
                        "raw_data": {
                            "id": position_id,
                            "title": title,
                            "category": category,
                            "description": description,
                            "employment_type": employment_type,
                            "work_setting": work_setting,
                            "travel_requirements": travel_reqs,
                            "salary_type": salary_type,
                            "salary_value": salary_value,
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "company_name": company_name,
                            "skills": skills,
                            "education_requirements": education_reqs,
                            "experience_requirements": experience_reqs
                        }
                    }
                    
        except ValueError:
            raise
        except Exception as e:
            logging.error(f"Failed to fetch profile text for {entity_type} ID {entity_id}: {str(e)}")
            raise
    
    def _format_experience(self, experience_list: list) -> str:
        """
        Format experience JSON into readable text for embedding.
        
        Expected formats:
        - [{"title": "...", "company": "...", "duration": "...", "description": "..."}]
        - [{"position": "...", "employer": "...", "startDate": "...", "endDate": "...", "responsibilities": "..."}]
        
        Handles various field name variations.
        """
        if not experience_list:
            return ""
        
        exp_texts = []
        for exp in experience_list:
            if isinstance(exp, dict):
                parts = []
                
                # Job title (try multiple field names)
                title = exp.get("title") or exp.get("position") or exp.get("jobTitle")
                if title:
                    parts.append(title)
                
                # Company/Employer
                company = exp.get("company") or exp.get("employer") or exp.get("companyName")
                if company:
                    parts.append(f"at {company}")
                
                # Duration/Dates
                duration = exp.get("duration")
                if duration:
                    parts.append(f"({duration})")
                elif exp.get("startDate") or exp.get("endDate"):
                    start = exp.get("startDate", "")
                    end = exp.get("endDate", "Present")
                    if start or end:
                        parts.append(f"({start} - {end})")
                
                # Years of experience
                years = exp.get("years") or exp.get("yearsOfExperience")
                if years:
                    parts.append(f"({years} years)")
                
                # Description/Responsibilities
                description = (exp.get("description") or 
                             exp.get("responsibilities") or 
                             exp.get("details"))
                if description:
                    # Truncate very long descriptions
                    desc_text = str(description)[:200]
                    if len(str(description)) > 200:
                        desc_text += "..."
                    parts.append(f"- {desc_text}")
                
                if parts:
                    exp_texts.append(" ".join(parts))
        
        return "; ".join(exp_texts)
    
    def _format_education(self, education_list: list) -> str:
        """
        Format education JSON into readable text for embedding.
        
        Expected formats:
        - [{"degree": "...", "institution": "...", "year": "...", "field": "..."}]
        - [{"degreeName": "...", "school": "...", "graduationYear": "...", "major": "..."}]
        
        Handles various field name variations.
        """
        if not education_list:
            return ""
        
        edu_texts = []
        for edu in education_list:
            if isinstance(edu, dict):
                parts = []
                
                # Degree name (try multiple field names)
                degree = edu.get("degree") or edu.get("degreeName") or edu.get("degreeType")
                if degree:
                    parts.append(degree)
                
                # Field of study/Major
                field = edu.get("field") or edu.get("major") or edu.get("fieldOfStudy")
                if field:
                    parts.append(f"in {field}")
                
                # Institution/School
                institution = edu.get("institution") or edu.get("school") or edu.get("university")
                if institution:
                    parts.append(f"from {institution}")
                
                # Year/Graduation year
                year = edu.get("year") or edu.get("graduationYear") or edu.get("endDate")
                if year:
                    parts.append(f"({year})")
                
                # GPA (if significant)
                gpa = edu.get("gpa")
                if gpa and float(gpa) >= 3.5:  # Only include high GPAs
                    parts.append(f"GPA: {gpa}")
                
                if parts:
                    edu_texts.append(" ".join(parts))
        
        return "; ".join(edu_texts)
    
    def test_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                logging.info("Database connection test successful")
                return True
        except Exception as e:
            logging.error(f"Database connection test failed: {str(e)}")
            return False
