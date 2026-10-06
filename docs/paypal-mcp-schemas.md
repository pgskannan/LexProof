# PayPal sandbox MCP input schemas

Dumped 2026-10-06 from `https://mcp.sandbox.paypal.com/sse` via `scripts/paypal_spike.py --schema`.

`create_invoice` does not use the REST invoice body. Currency is the top-level `currency_code`. The recipient is `primary_recipients[0].billing_info.email_address`. Line amounts are `items[].quantity` times `items[].unit_amount.value`. Keys outside these schemas are ignored by PayPal and denied by the guard.


## create_invoice

`json
{
  "type": "object",
  "properties": {
    "currency_code": {
      "type": "string",
      "description": "The three-character ISO-4217 currency code for the invoice (for example, USD). Applies to every monetary amount on the invoice."
    },
    "invoice_number": {
      "type": "string",
      "description": "The invoice number. If omitted, PayPal auto-increments from the last invoice number used."
    },
    "invoice_date": {
      "type": "string",
      "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])$",
      "description": "The invoice date in yyyy-MM-DD format."
    },
    "reference": {
      "type": "string",
      "description": "A reference value, such as a purchase order number."
    },
    "note": {
      "type": "string",
      "description": "A note to the invoice recipient. Also appears on the invoice notification email."
    },
    "invoicer_business_name": {
      "type": "string",
      "maxLength": 300,
      "description": "The business name of the invoicer."
    },
    "invoicer_given_name": {
      "type": "string",
      "description": "The first name of the invoicer."
    },
    "invoicer_surname": {
      "type": "string",
      "description": "The last name of the invoicer."
    },
    "invoicer_email_address": {
      "type": "string",
      "description": "The email address of the invoicer."
    },
    "invoicer_tax_id": {
      "type": "string",
      "description": "The invoicer's tax ID."
    },
    "invoicer_address_line_1": {
      "type": "string",
      "description": "The first line of the invoicer's address, for example, number and street."
    },
    "invoicer_address_line_2": {
      "type": "string",
      "description": "The second line of the invoicer's address, for example, suite or apartment number."
    },
    "invoicer_city": {
      "type": "string",
      "description": "The city, town, or village of the invoicer's address."
    },
    "invoicer_state": {
      "type": "string",
      "description": "The state or province of the invoicer's address."
    },
    "invoicer_postal_code": {
      "type": "string",
      "description": "The postal code of the invoicer's address."
    },
    "invoicer_country_code": {
      "type": "string",
      "pattern": "^([A-Z]{2}|C2)$",
      "description": "The two-character ISO 3166-1 country code of the invoicer's address (for example, US or GB)."
    },
    "primary_recipients": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "billing_info": {
            "type": "object",
            "properties": {
              "business_name": {
                "type": "string",
                "description": "The business name of the invoice recipient."
              },
              "name": {
                "type": "object",
                "properties": {
                  "given_name": {
                    "type": "string",
                    "description": "The first name of the person."
                  },
                  "surname": {
                    "type": "string",
                    "description": "The last name of the person."
                  }
                },
                "additionalProperties": false,
                "description": "name of the recipient"
              },
              "address": {
                "type": "object",
                "properties": {
                  "address_line_1": {
                    "type": "string",
                    "description": "The first line of the address, for example, number and street."
                  },
                  "address_line_2": {
                    "type": "string",
                    "description": "The second line of the address, for example, suite or apartment number."
                  },
                  "admin_area_2": {
                    "type": "string",
                    "description": "A city, town, or village."
                  },
                  "admin_area_1": {
                    "type": "string",
                    "description": "The highest-level sub-division in a country, such as a state or province."
                  },
                  "postal_code": {
                    "type": "string",
                    "description": "The postal code, which is the zip code or equivalent."
                  },
                  "country_code": {
                    "type": "string",
                    "pattern": "^([A-Z]{2}|C2)$",
                    "description": "The two-character ISO 3166-1 country code (for example, US or GB)."
                  }
                },
                "additionalProperties": false,
                "description": "The address of the invoice recipient."
              },
              "email_address": {
                "type": "string",
                "description": "email address of the recipient"
              },
              "phones": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "country_code": {
                      "type": "string",
                      "description": "The country calling code, in E.164 format (for example, '1' for the United States)."
                    },
                    "national_number": {
                      "type": "string",
                      "description": "The national number, in E.164 format."
                    },
                    "phone_type": {
                      "type": "string",
                      "enum": [
                        "FAX",
                        "HOME",
                        "MOBILE",
                        "OTHER",
                        "PAGER"
                      ],
                      "description": "The type of phone number."
                    }
                  },
                  "required": [
                    "country_code",
                    "national_number",
                    "phone_type"
                  ],
                  "additionalProperties": false,
                  "description": "phone object"
                },
                "description": "The invoice recipient's phone numbers."
              },
              "additional_info": {
                "type": "string",
                "maxLength": 40,
                "description": "Any additional information about the recipient."
              },
              "language": {
                "type": "string",
                "pattern": "^[a-z]{2}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$",
                "description": "The BCP-47 language tag used for the recipient's email notification (for example, 'en-US'). Only used when the recipient has no PayPal account."
              }
            },
            "additionalProperties": false,
            "description": "The billing information of the invoice recipient"
          },
          "shipping_info": {
            "type": "object",
            "properties": {
              "business_name": {
                "type": "string",
                "description": "The business name for the shipping destination."
              },
              "name": {
                "type": "object",
                "properties": {
                  "given_name": {
                    "type": "string",
                    "description": "The first name of the person."
                  },
                  "surname": {
                    "type": "string",
                    "description": "The last name of the person."
                  }
                },
                "additionalProperties": false,
                "description": "The name for the shipping destination."
              },
              "address": {
                "type": "object",
                "properties": {
                  "address_line_1": {
                    "type": "string",
                    "description": "The first line of the address, for example, number and street."
                  },
                  "address_line_2": {
                    "type": "string",
                    "description": "The second line of the address, for example, suite or apartment number."
                  },
                  "admin_area_2": {
                    "type": "string",
                    "description": "A city, town, or village."
                  },
                  "admin_area_1": {
                    "type": "string",
                    "description": "The highest-level sub-division in a country, such as a state or province."
                  },
                  "postal_code": {
                    "type": "string",
                    "description": "The postal code, which is the zip code or equivalent."
                  },
                  "country_code": {
                    "type": "string",
                    "pattern": "^([A-Z]{2}|C2)$",
                    "description": "The two-character ISO 3166-1 country code (for example, US or GB)."
                  }
                },
                "additionalProperties": false,
                "description": "The shipping address."
              }
            },
            "additionalProperties": false,
            "description": "The shipping information of the invoice recipient."
          }
        },
        "additionalProperties": false
      },
      "description": "The recipients who will be billed for this invoice."
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "The name of the item"
          },
          "description": {
            "type": "string",
            "description": "The description of the item."
          },
          "quantity": {
            "type": "string",
            "description": "The quantity of the item that the invoicer provides to the payer. Value is from -1000000 to 1000000. Supports up to five decimal places. Cast to string"
          },
          "unit_amount": {
            "type": "object",
            "properties": {
              "currency_code": {
                "type": "string",
                "description": "The three-character ISO-4217 currency code that identifies the currency."
              },
              "value": {
                "type": "string",
                "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
                "description": "The amount, as a signed decimal string with up to 2 decimal places (e.g. '50.00')."
              }
            },
            "required": [
              "currency_code",
              "value"
            ],
            "additionalProperties": false,
            "description": "The unit price of the item. Does not include tax or discount."
          },
          "tax": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "description": "The name of the tax applied on the item, for example 'Sales Tax'."
              },
              "percent": {
                "type": "string",
                "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
                "description": "The tax rate, as a percent value from 0 to 100. Supports up to five decimal places."
              },
              "tax_note": {
                "type": "string",
                "description": "A note about the tax, used to track tax-related data."
              }
            },
            "required": [
              "name",
              "percent"
            ],
            "additionalProperties": false,
            "description": "tax object"
          },
          "discount": {
            "type": "object",
            "properties": {
              "percent": {
                "type": "string",
                "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
                "description": "The discount as a percent value, from 0 to 100. Supports up to five decimal places. Mutually exclusive with amount -- set only one."
              },
              "amount": {
                "type": "object",
                "properties": {
                  "currency_code": {
                    "type": "string",
                    "description": "The three-character ISO-4217 currency code that identifies the currency."
                  },
                  "value": {
                    "type": "string",
                    "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
                    "description": "The amount, as a signed decimal string with up to 2 decimal places (e.g. '50.00')."
                  }
                },
                "required": [
                  "currency_code",
                  "value"
                ],
                "additionalProperties": false,
                "description": "The discount as a fixed amount. Mutually exclusive with percent -- set only one."
              }
            },
            "additionalProperties": false,
            "description": "The discount for this line item, subtracted from the item total."
          },
          "item_date": {
            "type": "string",
            "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])$",
            "description": "The date, in yyyy-MM-DD format, when the item or service was provided."
          },
          "unit_of_measure": {
            "type": "string",
            "enum": [
              "QUANTITY",
              "HOURS",
              "AMOUNT"
            ],
            "description": "The unit of measure for the invoiced item"
          }
        },
        "required": [
          "name",
          "quantity",
          "unit_amount"
        ],
        "additionalProperties": false,
        "description": "invoice line item object"
      },
      "description": "The line items on the invoice."
    },
    "allow_tip": {
      "type": "boolean",
      "description": "Whether the payer can add a tip when paying. Not available in Hong Kong, Taiwan, India, or Japan."
    },
    "theme_color": {
      "type": "string",
      "pattern": "^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$",
      "description": "The primary color used to render the invoice, as a hex color code (e.g. #000000). If omitted, the default theme is used."
    },
    "shipping_cost": {
      "type": "string",
      "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
      "description": "The shipping cost for the invoice, in the invoice's currency_code."
    },
    "enable_pay_by_bank": {
      "type": "boolean",
      "description": "Whether to enable PAY_BY_BANK as a payment method for this invoice, letting the payer pay directly from their bank account. Available only for US-based merchants and invoices with USD currency."
    },
    "pay_by_bank_exclusive_above_threshold": {
      "type": "boolean",
      "description": "When true, PAY_BY_BANK becomes the only available payment method once the invoice total exceeds PayPal's system-defined threshold ($1000), disabling all other payment methods above that threshold."
    },
    "allow_partial_payment": {
      "type": "boolean",
      "description": "Whether the invoice allows a partial payment. If false, the invoice must be paid in full. If true, the invoice allows partial payments. Not available for users in India, Brazil, or Israel."
    },
    "minimum_partial_payment_amount": {
      "type": "string",
      "pattern": "^((-?[0-9]+)|(-?([0-9]+)?[.][0-9]+))$",
      "description": "The minimum amount allowed for a partial payment, in the invoice's currency_code. Valid only when allow_partial_payment is true."
    }
  },
  "required": [
    "currency_code",
    "primary_recipients",
    "items"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`

## create_order

`json
{
  "type": "object",
  "properties": {
    "currencyCode": {
      "type": "string",
      "enum": [
        "USD"
      ],
      "description": "Currency code of the amount."
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "The name of the item."
          },
          "quantity": {
            "type": "number",
            "description": "The item quantity. Must be a whole number.",
            "default": 1
          },
          "description": {
            "type": "string",
            "description": "The detailed item description."
          },
          "itemCost": {
            "type": "number",
            "description": "The cost of each item - upto 2 decimal points."
          },
          "taxPercent": {
            "type": "number",
            "description": "The tax percent for the specific item.",
            "default": 0
          },
          "itemTotal": {
            "type": "number",
            "description": "The total cost of this line item."
          }
        },
        "required": [
          "name",
          "itemCost",
          "itemTotal"
        ],
        "additionalProperties": false
      },
      "maxItems": 50
    },
    "discount": {
      "type": "number",
      "description": "The discount amount for the order.",
      "default": 0
    },
    "shippingCost": {
      "type": "number",
      "description": "The cost of shipping for the order.",
      "default": 0
    },
    "shippingAddress": {
      "anyOf": [
        {
          "type": "object",
          "properties": {
            "address_line_1": {
              "type": "string",
              "description": "The first line of the address, such as number and street, for example, `173 Drury Lane`.This field needs to pass the full address."
            },
            "address_line_2": {
              "type": "string",
              "description": "The second line of the address, for example, a suite or apartment number."
            },
            "admin_area_2": {
              "type": "string",
              "description": "A city, town, or village. Smaller than `admin_area_level_1`."
            },
            "admin_area_1": {
              "type": "string",
              "description": "The highest-level sub-division in a country, which is usually a province, state, or ISO-3166-2 subdivision. "
            },
            "postal_code": {
              "type": "string",
              "description": "The postal code, which is the ZIP code or equivalent. Typically required for countries with a postal code or an equivalent."
            },
            "country_code": {
              "type": "string",
              "minLength": 2,
              "maxLength": 2,
              "description": "The 2-character ISO 3166-1 code that identifies the country or region. Note: The country code for Great Britain is `GB` and not `UK` as used in the top-level domain names for that country."
            }
          },
          "additionalProperties": false,
          "description": "The shipping address for the order."
        },
        {
          "type": "null"
        }
      ],
      "description": "The shipping address for the order.",
      "default": null
    },
    "notes": {
      "anyOf": [
        {
          "anyOf": [
            {
              "not": {}
            },
            {
              "type": "string"
            }
          ]
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "returnUrl": {
      "type": "string",
      "default": "https://example.com/returnUrl"
    },
    "cancelUrl": {
      "type": "string",
      "default": "https://example.com/cancelUrl"
    }
  },
  "required": [
    "currencyCode",
    "items"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`

## create_refund

`json
{
  "type": "object",
  "properties": {
    "capture_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9_-]{15,32}$",
      "description": "The ID of the capture to refund."
    },
    "amount": {
      "type": "object",
      "properties": {
        "currency_code": {
          "type": "string"
        },
        "value": {
          "type": "string"
        }
      },
      "required": [
        "currency_code",
        "value"
      ],
      "additionalProperties": false,
      "description": "The amount to refund. If not specified, the full captured amount is refunded."
    },
    "invoice_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9_-]{1,127}$",
      "description": "The invoice ID that is used to track this payment."
    },
    "note_to_payer": {
      "type": "string",
      "description": "A note to the payer."
    }
  },
  "required": [
    "capture_id"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`

## get_invoice

`json
{
  "type": "object",
  "properties": {
    "invoice_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9_-]{1,127}$",
      "description": "The ID of the invoice to retrieve."
    }
  },
  "required": [
    "invoice_id"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`

## send_invoice

`json
{
  "type": "object",
  "properties": {
    "invoice_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9_-]{1,127}$",
      "description": "The ID of the invoice to send."
    },
    "note": {
      "type": "string",
      "description": "A note to the recipient."
    },
    "send_to_recipient": {
      "type": "boolean",
      "description": "Indicates whether to send the invoice to the recipient."
    },
    "additional_recipients": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Additional email addresses to which to send the invoice."
    }
  },
  "required": [
    "invoice_id"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`

## send_invoice_reminder

`json
{
  "type": "object",
  "properties": {
    "invoice_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9_-]{1,127}$",
      "description": "The ID of the invoice for which to send a reminder."
    },
    "subject": {
      "type": "string",
      "description": "The subject of the reminder email."
    },
    "note": {
      "type": "string",
      "description": "A note to the recipient."
    },
    "additional_recipients": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Additional email addresses to which to send the reminder."
    }
  },
  "required": [
    "invoice_id"
  ],
  "additionalProperties": false,
  "$schema": "http://json-schema.org/draft-07/schema#"
}
`
