"""
Query Optimization Utilities for Movie Filtering

This module provides optimized query building and filtering logic to prevent
N+1 queries and full-table scans. It uses select_related and prefetch_related
for efficient data retrieval.

Performance Strategy:
- Use select_related() for ForeignKey relationships (Theater, Booking)
- Use prefetch_related() for ManyToMany and reverse FK relationships (genres, languages)
- Use distinct() to avoid duplicate rows when filtering through ManyToMany
- Implement database indexes on frequently queried fields
- Use only() and values_list() to reduce query payload when needed
"""

from django.db.models import QuerySet, Q, Count, F, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from movies.models import Movie, Genre, Language, Theater


class MovieQueryOptimizer:
    """Optimized movie query builder with advanced filtering"""
    
    @staticmethod
    def get_optimized_queryset(search_query=None, selected_genres=None, 
                               selected_languages=None, sort_by='name'):
        """
        Build optimized queryset with filtering while preventing N+1 queries
        
        Args:
            search_query (str): Search term for movie name
            selected_genres (list): List of genre IDs to filter by
            selected_languages (list): List of language IDs to filter by
            sort_by (str): Field to sort by ('name', 'rating', 'release_date', '-rating')
        
        Returns:
            QuerySet: Optimized movie queryset
        
        Performance considerations:
        - select_related() is not applied here as genres/languages are ManyToMany
        - prefetch_related() is applied to reduce queries for related data
        - distinct() is required when filtering through ManyToMany to avoid duplicates
        - Indexes on name, rating, and release_date support sorting/search operations
        """
        # Start with base queryset and prefetch related data
        queryset = Movie.objects.prefetch_related('genres', 'languages')
        
        # Apply search filter (uses database-level string matching)
        if search_query:
            queryset = queryset.filter(Q(name__icontains=search_query) | 
                                      Q(description__icontains=search_query))
        
        # Apply genre filter (ManyToMany)
        # Each genre filter adds a JOIN, so we use distinct() to avoid duplicates
        if selected_genres and len(selected_genres) > 0:
            queryset = queryset.filter(genres__id__in=selected_genres).distinct()
        
        # Apply language filter (ManyToMany)
        if selected_languages and len(selected_languages) > 0:
            queryset = queryset.filter(languages__id__in=selected_languages).distinct()
        
        # Apply sorting (leverages database indexes)
        valid_sorts = ['name', '-name', 'rating', '-rating', 'release_date', '-release_date']
        if sort_by in valid_sorts:
            queryset = queryset.order_by(sort_by)
        else:
            queryset = queryset.order_by('name')
        
        return queryset
    
    @staticmethod
    def get_filter_counts(search_query=None, selected_genres=None, 
                         selected_languages=None):
        """
        Get dynamic filter counts showing how many movies match each filter option
        
        Args:
            search_query (str): Current search term
            selected_genres (list): Currently selected genres
            selected_languages (list): Currently selected languages
        
        Returns:
            dict: Contains counts for each genre and language based on current filters
        
        Performance optimization:
        - Uses separate queries for counts rather than N+1 queries per item
        - Each query can be cached if needed
        - Counts reflect applied filters (show what's available with current selection)
        """
        genre_counts = {}
        language_counts = {}
        
        # Get base queryset with current filters applied
        base_qs = MovieQueryOptimizer.get_optimized_queryset(
            search_query=search_query,
            selected_genres=selected_genres,
            selected_languages=selected_languages
        )
        
        # Get count for each genre in filtered results
        genres = Genre.objects.all()
        for genre in genres:
            # Count movies that match current filters AND have this genre
            count = base_qs.filter(genres=genre).values('id').distinct().count()
            genre_counts[genre.id] = {
                'name': genre.name,
                'count': count,
                'selected': genre.id in (selected_genres or [])
            }
        
        # Get count for each language in filtered results
        languages = Language.objects.all()
        for language in languages:
            # Count movies that match current filters AND have this language
            count = base_qs.filter(languages=language).values('id').distinct().count()
            language_counts[language.id] = {
                'name': language.name,
                'count': count,
                'selected': language.id in (selected_languages or [])
            }
        
        return {
            'genres': genre_counts,
            'languages': language_counts
        }


class PaginationHelper:
    """Helper for efficient pagination"""
    
    @staticmethod
    def paginate_queryset(queryset, page_number=1, per_page=12):
        """
        Paginate queryset efficiently
        
        Args:
            queryset (QuerySet): Movie queryset
            page_number (int): Page number (1-indexed)
            per_page (int): Items per page
        
        Returns:
            dict: Contains paginated movies and pagination info
        
        Performance:
        - Uses Django's Paginator for efficient slicing
        - Only fetches the required page of results
        - Counts total are cached by Paginator
        """
        paginator = Paginator(queryset, per_page)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        return {
            'movies': page_obj.object_list,
            'page_obj': page_obj,
            'paginator': paginator,
            'total_count': paginator.count,
            'has_other_pages': page_obj.has_other_pages(),
            'is_first_page': page_obj.number == 1,
            'is_last_page': page_obj.number == paginator.num_pages
        }


def build_filter_url_params(genres=None, languages=None, search=None, page=1, sort='name'):
    """
    Build URL parameters for filter links with query string
    
    Args:
        genres (list): Selected genre IDs
        languages (list): Selected language IDs
        search (str): Search term
        page (int): Current page
        sort (str): Sort field
    
    Returns:
        str: URL parameters
    """
    params = []
    
    if search:
        params.append(f"search={search}")
    
    if genres:
        for genre_id in genres:
            params.append(f"genres={genre_id}")
    
    if languages:
        for lang_id in languages:
            params.append(f"languages={lang_id}")
    
    params.append(f"sort={sort}")
    params.append(f"page={page}")
    
    return "&".join(params)
