import csv
from django.shortcuts import render
from .forms import CSVUploadForm
from .models import Costing, Categories, Committed_quotes, Committed_allocations, Claims, Claim_allocations, Hc_claims, Hc_claim_lines
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.template import loader
from django.db.models import Sum
from django.core.files.base import ContentFile
import json
import base64
import uuid
from django.core import serializers
from django.forms.models import model_to_dict
from django.core.files.storage import default_storage
from django.core.exceptions import ObjectDoesNotExist
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404
from decimal import Decimal

# OATH XERO INCLUDES
import os
from functools import wraps
from django.urls import reverse
from django.shortcuts import redirect
from xero_python.api_client import ApiClient, serialize
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from requests_oauthlib import OAuth2Session
from authlib.integrations.django_client import OAuth, token_update
from django.core.cache import cache
from django.dispatch import receiver

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
oauth = OAuth()
xero = oauth.register(
    name="xero",
    version="2",
    client_id=os.environ["CLIENT_ID"],
    client_secret=os.environ["CLIENT_SECRET"],
    endpoint_url="https://api.xero.com/",
    authorization_url="https://login.xero.com/identity/connect/authorize",
    access_token_url="https://identity.xero.com/connect/token",
    refresh_token_url="https://identity.xero.com/connect/token",
    scope="offline_access openid profile email accounting.transactions "
    "accounting.transactions.read accounting.reports.read "
    "accounting.journals.read accounting.settings accounting.settings.read "
    "accounting.contacts accounting.contacts.read accounting.attachments "
    "accounting.attachments.read assets projects"
)

api_client = ApiClient(
    Configuration(
        debug=True,  # app.config["DEBUG"],
        oauth2_token=OAuth2Token(
            client_id="client_id", client_secret="client_secret"
        ),
    ),
    pool_threads=1,
)

def login(request):
    redirect_uri = request.build_absolute_uri('authorise/')
    return oauth.xero.authorize_redirect(request, redirect_uri)

def oauth_callback(request):
    try:
        token = oauth.xero.authorize_access_token(request)
    except Exception as e:
        print(e)
        raise
    if token is None:
        return HttpResponse("Access Denied")
    store_xero_oauth2_token(token)

    return redirect('/backend/tenants/')


def logout():
    store_xero_oauth2_token(None)
    return redirect('/')


def xero_token_required(function):
    @wraps(function)
    def decorator(*args, **kwargs):
        xero_token = obtain_xero_oauth2_token()
        time = datetime.datetime.now().timestamp()
        if time > xero_token['expires_at']:
            new_token = oauth.xero.fetch_access_token(
                refresh_token=xero_token['refresh_token'],
                grant_type='refresh_token')
            store_xero_oauth2_token(new_token)
            xero_token = new_token

        if not xero_token:
            return redirect(reverse("oauth"))

        return function(*args, **kwargs)

    return decorator

@api_client.oauth2_token_getter
def obtain_xero_oauth2_token():
    return cache.get('token')


@api_client.oauth2_token_saver
def store_xero_oauth2_token(token):
    cache.set('token', token, None)


# Create a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

def contract_admin(request):
    print(settings.MEDIA_ROOT)
    form = CSVUploadForm()  # Instantiate your form 
    costings = Costing.objects.all().order_by('category__order_in_list', 'category__category', 'item')    # Convert each 'costing' object to a dictionary and add 'committed'
    costings = [model_to_dict(costing) for costing in costings]
    for costing in costings:
        category = Categories.objects.get(pk=costing['category'])
        costing['category'] = category.category
    committed_allocations = Committed_allocations.objects.all()
    # Calculate the sums for each item
    committed_allocations_sums = Committed_allocations.objects.values('item').annotate(total_amount=Sum('amount'))
    # Convert the sums to a dictionary for easier access in the template
    committed_allocations_sums_dict = {item['item']: item['total_amount'] for item in committed_allocations_sums}
    # Append 'committed' to 'items'
    for costing in costings:
        costing['committed'] = committed_allocations_sums_dict.get(costing['item'], 0)    # New: Retrieve a list of items for the dropdown
    # Retrieve all Hc_claim_lines objects to create a dictionary of items | hc_claimed
    hc_claim_lines_sums = Hc_claim_lines.objects.values('item_id').annotate(total_amount=Sum('amount'))
    hc_claim_lines_sums_dict = {item['item_id']: item['total_amount'] for item in hc_claim_lines_sums}
    # Append 'hc_claimed' to 'costings'
# Append 'hc_claimed' and 'hc_claimed_amount' to 'costings' --> DOESN"T WORK!
    for costing in costings:
        hc_claimed_amount = hc_claim_lines_sums_dict.get(costing['id'])
        if hc_claimed_amount is not None:
            costing['hc_claimed_amount'] = str(hc_claimed_amount)
        else:
            costing['hc_claimed_amount'] = '0.00'
        costing['hc_claimed'] = hc_claimed_amount or 0
    items = [{'item': costing['item'], 'uncommitted': costing['uncommitted'], 'committed': costing['committed']} for costing in costings]
    # Retrieve all Committed_quotes and Committed_allocations objects
    committed_quotes = Committed_quotes.objects.all()
    logger.info(committed_quotes)
    committed_quotes_json = serializers.serialize('json', committed_quotes)
    committed_allocations_json = serializers.serialize('json', committed_allocations)
    # Retrieve all Claims and Claim_allocations objects
    claims = Claims.objects.all()
    claims_json = serializers.serialize('json', claims)
    claim_allocations = Claim_allocations.objects.all()
    claim_allocations_json = serializers.serialize('json', claim_allocations)
    total_committed = sum(costing['committed'] for costing in costings)
    hc_claimed = [
    {
        'id': costing['id'],
        'amount': hc_claim_lines_sums_dict.get(str(costing['id']), '0.00')
    }
    for costing in costings
    ]
    totals = {
        'total_contract_budget': Costing.objects.aggregate(Sum('contract_budget'))['contract_budget__sum'] or 0,
        'total_committed': total_committed,
        'total_uncommitted': Costing.objects.aggregate(Sum('uncommitted'))['uncommitted__sum'] or 0,
        'total_complete_on_site': Costing.objects.aggregate(Sum('complete_on_site'))['complete_on_site__sum'] or 0,
        'total_hc_next_claim': Costing.objects.aggregate(Sum('hc_next_claim'))['hc_next_claim__sum'] or 0,
        'total_hc_received': Costing.objects.aggregate(Sum('hc_received'))['hc_received__sum'] or 0,
        'total_sc_invoiced': Costing.objects.aggregate(Sum('sc_invoiced'))['sc_invoiced__sum'] or 0,
        'total_sc_paid': Costing.objects.aggregate(Sum('sc_paid'))['sc_paid__sum'] or 0,
    }
    totals['total_forecast_budget'] = totals['total_committed'] + totals['total_uncommitted']
    context = {
        'form': form,
        'costings': costings,
        'items': items,  # Add items to context
        'totals': totals,
        'committed_quotes': committed_quotes_json,
        'committed_allocations': committed_allocations_json,  # Add committed_allocations to context
        'claims': claims_json,
        'claim_allocations': claim_allocations_json,  # Add claims and claim_allocations to context
        'hc_claim_lines_sums': hc_claim_lines_sums_dict,
        'hc_claimed': json.dumps(hc_claimed, cls=DecimalEncoder),
    }
    return render(request, 'contract_admin.html', context)

def upload_csv(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            print(next(reader))  # This will print the first row of the CSV to your console
            # Delete existing data
            Costing.objects.all().delete()
            for row in reader:
                category, created = Categories.objects.get_or_create(category=row['category'])
                Costing.objects.create(
                    category=category,
                    item=row['item'],
                    contract_budget=row['contract_budget'],
                    uncommitted=row['uncommitted'],
                    complete_on_site=row['complete_on_site'],
                    hc_next_claim=row['hc_next_claim'],
                    hc_received=row['hc_received'],
                    sc_invoiced=row['sc_invoiced'],
                    sc_paid=row['sc_paid'],
                    notes=row['notes']
                )
            return JsonResponse({"message": "CSV file uploaded successfully"}, status=200)
        else:
            return JsonResponse({"message": str(form.errors)}, status=400)
    else:
        form = CSVUploadForm()

@csrf_exempt
def upload_categories(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            logger.info('CSV file decoded and reader created')
            Categories.objects.all().delete()
            logger.info('All existing Categories objects deleted')
            for row in reader:
                Categories.objects.create(
                    category=row['category'],
                    order_in_list=row['order_in_list']
                )
                logger.info('Created new Categories object: %s', row)
            return JsonResponse({"message": "CSV file uploaded successfully"}, status=200)
        else:
            logger.error('Form is not valid: %s', form.errors)
            return JsonResponse({"message": str(form.errors)}, status=400)
    else:
        form = CSVUploadForm()
        logger.info('GET request received, CSVUploadForm created')


def update_costs(request):
    if request.method == 'POST':
        costing_id = request.POST.get('id')
        uncommitted = request.POST.get('uncommitted')
        # Make sure you're handling type conversion and validation properly here
        try:
            costing = Costing.objects.get(id=costing_id)
            costing.uncommitted = uncommitted
            costing.save()
            return JsonResponse({'status': 'success'})
        except Costing.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Costing not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
    
@csrf_exempt
def update_complete_on_site(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        costing_id = data.get('id')
        complete_on_site_data = data.get('complete_on_site')
        try:
            complete_on_site = float(complete_on_site_data)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid complete_on_site value'}, status=400)
        try:
            costing = Costing.objects.get(pk=costing_id)
            costing.complete_on_site = complete_on_site
            costing.save()
            return JsonResponse({'status': 'success'})
        except Costing.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Costing not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)



@csrf_exempt
def commit_data(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        total_cost = data['total_cost']
        pdf_data = data['pdf']
        supplier = data['supplier']
        allocations = data.get('allocations')
        format, imgstr = pdf_data.split(';base64,')
        ext = format.split('/')[-1]
        data = ContentFile(base64.b64decode(imgstr), name='temp.' + ext)
        quote = Committed_quotes.objects.create(total_cost=total_cost, pdf=data, supplier=supplier)  # Add supplier here
        for item in allocations:
            amount = item['amount']
            description = item.get('description', '')  # Get the description, default to '' if not present
            if amount == '':
                amount = '0'
            Committed_allocations.objects.create(quote=quote, item=item['item'], amount=amount, description=description)  # Include description here
            # Update the Costing.uncommitted field
            uncommitted = item['uncommitted']
            Costing.objects.filter(item=item['item']).update(uncommitted=uncommitted)
        return JsonResponse({'status': 'success'})

@csrf_exempt
def update_costing(request):
    if request.method == 'POST':
        costing_id = request.POST.get('costing_id')
        uncommitted = request.POST.get('uncommitted')
        # Get the Costing object and update it
        costing = Costing.objects.get(id=costing_id)
        costing.uncommitted = uncommitted
        costing.save()
        # Return a JSON response
        return JsonResponse({'status': 'success'})

@csrf_exempt
def delete_quote(request):
    if request.method == 'DELETE':
        data = json.loads(request.body)
        quote_id = data.get('id')
        if quote_id is not None:
            try:
                quote = Committed_quotes.objects.get(pk=quote_id)
                quote.delete()
                return JsonResponse({'status': 'success'})
            except Committed_quotes.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Quote not found'}, status=404)
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@csrf_exempt
def update_quote(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        quote_id = data.get('quote_id')
        total_cost = data.get('total_cost')
        supplier = data.get('supplier')
        allocations = data.get('allocations')
        try:
            quote = Committed_quotes.objects.get(pk=quote_id)
        except Committed_quotes.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Quote not found'})
        quote.total_cost = total_cost
        quote.supplier = supplier
        quote.save()
        # Delete the existing allocations for the quote
        Committed_allocations.objects.filter(quote_id=quote_id).delete()
        # Save the new allocations
        for allocation in allocations:
            alloc = Committed_allocations(quote_id=quote_id, item=allocation['item'], amount=allocation['amount'])
            alloc.save()
            # Update the Costing.uncommitted field
            uncommitted = allocation['uncommitted']
            Costing.objects.filter(item=allocation['item']).update(uncommitted=uncommitted)
        return JsonResponse({'status': 'success'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
@csrf_exempt
def commit_claim_data(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        total_cost = data['total_cost']
        pdf_data = data['pdf']
        allocations = data.get('allocations')
        format, imgstr = pdf_data.split(';base64,')
        ext = format.split('/')[-1]
        data = ContentFile(base64.b64decode(imgstr), name='temp.' + ext)
        claim = Claims.objects.create(total=total_cost, pdf=data)  # Create a new claim
        for item in allocations:
            amount = item['amount']
            if amount == '':
                amount = '0'
            associated_quote_pk = item['associated_quote'] 
            associated_quote = get_object_or_404(Committed_quotes, pk=associated_quote_pk) 
            Claim_allocations.objects.create(claim=claim, item=item['item'], amount=amount, associated_quote=associated_quote) 
        return JsonResponse({'status': 'success'})
    
@csrf_exempt
def commit_hc_claim(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        hc_claim = Hc_claims.objects.create()
        for item in data['data']:
            if item['amount'] != '0':
                Hc_claim_lines.objects.create(
                    hc_claim=hc_claim,
                    item_id=item['itemId'],
                    amount=item['amount']
                )
        return JsonResponse({'hc_claim': hc_claim.hc_claim}, status=201)
    return JsonResponse({'error': 'Invalid request'}, status=400)

