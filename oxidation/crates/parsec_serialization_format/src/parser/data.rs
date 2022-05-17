// Parsec Cloud (https://parsec.cloud) Copyright (c) BSLv1.1 (eventually AGPLv3) 2016-2021 Scille SAS

use miniserde::Deserialize;
use proc_macro2::TokenStream;
use quote::quote;
use syn::Ident;

use super::{quote_fields, Field, Vis};

#[derive(Deserialize)]
pub(crate) struct Data {
    label: String,
    #[serde(rename = "type")]
    ty: String,
    other_fields: Vec<Field>,
}

impl Data {
    pub(crate) fn quote(&self) -> TokenStream {
        let name: Ident =
            syn::parse_str(&format!("{}Data", self.label)).unwrap_or_else(|_| unreachable!());
        let name_type: Ident =
            syn::parse_str(&format!("{}DataType", self.label)).unwrap_or_else(|_| unreachable!());
        let ty = &self.ty;
        let fields = quote_fields(&self.other_fields, Vis::Public);
        quote! {
            #[serde_with::serde_as]
            #[derive(Debug, Clone, ::serde::Serialize, ::serde::Deserialize, PartialEq, Eq)]
            pub struct #name {
                #[serde(rename="type")]
                pub ty: #name_type,
                #fields
            }

            #[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
            pub struct #name_type;

            impl Serialize for #name_type {
                fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
                where
                    S: ::serde::ser::Serializer,
                {
                    serializer.serialize_str(#ty)
                }
            }

            impl<'de> Deserialize<'de> for #name_type {
                fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
                where
                    D: serde::de::Deserializer<'de>,
                {
                    struct Visitor;

                    impl<'de> serde::de::Visitor<'de> for Visitor {
                        type Value = #name_type;

                        fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                            formatter.write_str(concat!("the `", #ty, "` string"))
                        }

                        fn visit_str<E>(self, v: &str) -> Result<Self::Value, E>
                        where
                            E: serde::de::Error,
                        {
                            if v == #ty {
                                Ok(#name_type)
                            } else {
                                Err(serde::de::Error::invalid_type(
                                    serde::de::Unexpected::Str(v),
                                    &self,
                                ))
                            }
                        }
                    }

                    deserializer.deserialize_str(Visitor)
                }
            }
        }
    }
}
